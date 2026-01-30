#version 300 es
precision highp float;

// Chromatic Waves Shader
// Original source from Shadertoy (author unknown)
// If you know the original author, please open an issue to properly credit them

// Standard uniforms
uniform float iTime;
uniform vec2 iResolution;

// MQTT-controllable uniforms
uniform float speed;          // Animation speed (default: 1.0)
uniform float waveFrequency;  // Wave frequency (default: 3.1415)
uniform float rippleSpeed;    // Ripple animation speed (default: 4.0)
uniform float rippleScale;    // Ripple scale (default: 8.0)
uniform float colorIntensity; // Overall color intensity (default: 1.0)

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

void mainImage( out vec4 fragColor_out, in vec2 fragCoord )
{
	vec2 uv = fragCoord.xy / iResolution.xy;
    float t = iTime * speed;

    float s3 = 0.5+0.5*sin(t+uv.x*waveFrequency*(sin(t)+4.0));
    float s4 = 0.5+0.25*sin(t+uv.x*waveFrequency*(sin(t)*2.0+2.0));

    float s1 = 0.5+0.5*sin(t+uv.x*waveFrequency+20.*(sin(t)+4.0));
    float s2 = 0.5+0.25*sin(t+uv.x*waveFrequency+0.5*(sin(t)*2.0+2.0));

    float r = pow(1.0-sqrt( abs(uv.y-s1)),1.5 );
    float g = pow(1.0-sqrt( abs(uv.y-s2)),1.5 );
    float b1 = pow(1.0-sqrt( abs(uv.y-s3+s4)),1.5 );

    float b = 1.0*(r+g)*b1;

    const float pi = 3.14159265;
    vec2 ar = vec2(iResolution.x/iResolution.y, 1);
    float rippleTime = t * rippleSpeed;
    float c = smoothstep(.0, .2, cos( rippleTime + rippleScale*pi*length(ar*uv-ar*.5) ) );

	fragColor_out = vec4( r*c*colorIntensity, g*c*colorIntensity, b*(1.0-c)*colorIntensity, 1 );
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
