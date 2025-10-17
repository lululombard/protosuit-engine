#version 300 es
precision highp float;

// Sun Shader
// Based on https://www.shadertoy.com/view/lsf3RH by trisomie21

// Standard uniforms
uniform float iTime;
uniform vec2 iResolution;

// MQTT-controllable uniforms
uniform float speed;          // Animation speed (default: 1.0)
uniform float brightness;     // Sun brightness/activity (default: 0.5)
uniform float coronaScale;    // Corona intensity (default: 1.0)
uniform float turbulence;     // Surface turbulence (default: 1.0)
uniform vec3 sunColor;        // Sun base color (default: orange)
uniform vec3 coronaColor;     // Corona color (default: orange-red)

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

float snoise(vec3 uv, float res)
{
	const vec3 s = vec3(1e0, 1e2, 1e4);

	uv *= res;

	vec3 uv0 = floor(mod(uv, res))*s;
	vec3 uv1 = floor(mod(uv+vec3(1.), res))*s;

	vec3 f = fract(uv); f = f*f*(3.0-2.0*f);

	vec4 v = vec4(uv0.x+uv0.y+uv0.z, uv1.x+uv0.y+uv0.z,
		      	  uv0.x+uv1.y+uv0.z, uv1.x+uv1.y+uv0.z);

	vec4 r = fract(sin(v*1e-3)*1e5);
	float r0 = mix(mix(r.x, r.y, f.x), mix(r.z, r.w, f.x), f.y);

	r = fract(sin((v + uv1.z - uv0.z)*1e-3)*1e5);
	float r1 = mix(mix(r.x, r.y, f.x), mix(r.z, r.w, f.x), f.y);

	return mix(r0, r1, f.z)*2.-1.;
}

// Procedural noise texture replacement
float noiseTexture(vec2 uv)
{
	vec2 p = floor(uv * 256.0);
	float n = p.x + p.y * 57.0;
	n = fract(sin(n) * 43758.5453);
	return n;
}

vec3 textureNoise(vec2 uv)
{
	float r = noiseTexture(uv);
	float g = noiseTexture(uv + vec2(0.1, 0.3));
	float b = noiseTexture(uv + vec2(0.5, 0.7));
	return vec3(r, g, b);
}

void mainImage( out vec4 fragColor_out, in vec2 fragCoord )
{
	// Simulate audio reactivity with oscillating values
	float time = iTime * speed;
	float freq1 = 0.5 + 0.3 * sin(time * 1.3);
	float freq2 = 0.5 + 0.3 * sin(time * 1.7);
	float freq3 = 0.5 + 0.3 * sin(time * 2.1);

	float localBrightness = brightness * 0.5 + (freq1 * 0.15 + freq2 * 0.15) * turbulence;
	float radius = 0.24 + localBrightness * 0.2;
	float invRadius = 1.0/radius;

	vec3 orange = sunColor;
	vec3 orangeRed = coronaColor;
	float animTime = time * 0.1;
	float aspect = iResolution.x/iResolution.y;
	vec2 uv = fragCoord.xy / iResolution.xy;
	vec2 p = -0.5 + uv;
	p.x *= aspect;

	float fade = pow( length( 2.0 * p ), 0.5 );
	float fVal1 = 1.0 - fade;
	float fVal2 = 1.0 - fade;

	float angle = atan( p.x, p.y )/6.2832;
	float dist = length(p);
	vec3 coord = vec3( angle, dist, animTime * 0.1 );

	float newTime1 = abs( snoise( coord + vec3( 0.0, -animTime * ( 0.35 + localBrightness * 0.001 ), animTime * 0.015 ), 15.0 ) );
	float newTime2 = abs( snoise( coord + vec3( 0.0, -animTime * ( 0.15 + localBrightness * 0.001 ), animTime * 0.015 ), 45.0 ) );

	for( int i=1; i<=7; i++ ){
		float power = pow( 2.0, float(i + 1) );
		fVal1 += ( 0.5 / power ) * snoise( coord + vec3( 0.0, -animTime, animTime * 0.2 ), ( power * ( 10.0 ) * ( newTime1 + 1.0 ) ) );
		fVal2 += ( 0.5 / power ) * snoise( coord + vec3( 0.0, -animTime, animTime * 0.2 ), ( power * ( 25.0 ) * ( newTime2 + 1.0 ) ) );
	}

	float corona = pow( fVal1 * max( 1.1 - fade, 0.0 ), 2.0 ) * 50.0;
	corona += pow( fVal2 * max( 1.1 - fade, 0.0 ), 2.0 ) * 50.0;
	corona *= 1.2 - newTime1;
	corona *= coronaScale;

	vec3 starSphere = vec3( 0.0 );

	vec2 sp = -1.0 + 2.0 * uv;
	sp.x *= aspect;
	sp *= ( 2.0 - localBrightness );
	float r = dot(sp,sp);
	float f = (1.0-sqrt(abs(1.0-r)))/(r) + localBrightness * 0.5;

	if( dist < radius ){
		corona *= pow( dist * invRadius, 24.0 );
		vec2 newUv;
		newUv.x = sp.x*f;
		newUv.y = sp.y*f;
		newUv += vec2( animTime, 0.0 );

		// Use procedural noise instead of texture
		vec3 texSample = textureNoise( newUv * 2.0 );
		float uOff = ( texSample.g * localBrightness * 4.5 + animTime );
		vec2 starUV = newUv + vec2( uOff, 0.0 );
		starSphere = textureNoise( starUV * 2.0 ) * turbulence;
	}

	float starGlow = min( max( 1.0 - dist * ( 1.0 - localBrightness ), 0.0 ), 1.0 );

	fragColor_out.rgb = vec3( f * ( 0.75 + localBrightness * 0.3 ) * orange ) + starSphere + corona * orange + starGlow * orangeRed;
	fragColor_out.a = 1.0;
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
