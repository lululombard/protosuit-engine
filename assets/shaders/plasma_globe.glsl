#version 300 es
precision highp float;

// Plasma Globe Shader
// Created by nimitz (2014-09-10)
// https://www.shadertoy.com/view/XsjXRm
// License Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported License

// Standard uniforms
uniform float iTime;
uniform vec2 iResolution;

// MQTT-controllable uniforms
uniform float speed;          // Animation speed (default: 1.0)
uniform float numRays;        // Number of plasma rays (default: 13.0)
uniform float squiggliness;   // Path variation amount (default: 0.5, lower = smoother)
uniform float rotationSpeed;  // Globe rotation speed (default: 1.0)
uniform vec3 plasmaColor1;    // Primary plasma color (default: cyan)
uniform vec3 plasmaColor2;    // Secondary plasma color (default: magenta)
uniform float brightness;     // Overall brightness (default: 1.0)

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

#define VOLUMETRIC_STEPS 19
#define MAX_ITER 35
#define FAR 6.

mat2 mm2(in float a){float c = cos(a), s = sin(a);return mat2(c,-s,s,c);}

float hash(float n){return fract(sin(n)*43758.5453);}

// Procedural 3D noise (replaces texture lookup)
float noise(in vec3 p)
{
	vec3 ip = floor(p);
    vec3 fp = fract(p);
	fp = fp*fp*(3.0-2.0*fp);

	float n = ip.x + ip.y*57.0 + ip.z*113.0;
	float a = hash(n);
	float b = hash(n+1.0);
	float c = hash(n+57.0);
	float d = hash(n+58.0);
	float e = hash(n+113.0);
	float f = hash(n+114.0);
	float g = hash(n+170.0);
	float h = hash(n+171.0);

	float res = mix(mix(mix(a,b,fp.x), mix(c,d,fp.x), fp.y),
	                mix(mix(e,f,fp.x), mix(g,h,fp.x), fp.y), fp.z);
	return res;
}

mat3 m3 = mat3( 0.00,  0.80,  0.60,
              -0.80,  0.36, -0.48,
              -0.60, -0.48,  0.64 );

float flow(in vec3 p, in float t)
{
	float z=2.;
	float rz = 0.;
	vec3 bp = p;
	for (float i= 1.;i < 5.;i++ )
	{
		p += iTime*speed*.1;
		rz+= (sin(noise(p+t*0.8)*6.)*0.5+0.5) /z;
		p = mix(bp,p,0.6);
		z *= 2.;
		p *= 2.01;
        p*= m3;
	}
	return rz;
}

// Smoother wave function (reduced squiggliness)
float sins(in float x)
{
 	float rz = 0.;
    float z = 2.;
    for (float i= 0.;i < 3.;i++ )
	{
        rz += abs(fract(x*1.4)-0.5)/z;
        x *= 1.3;
        z *= 1.15;
        x -= iTime*speed*.65*z;
    }
    return rz;
}

float segm( vec3 p, vec3 a, vec3 b)
{
    vec3 pa = p - a;
	vec3 ba = b - a;
	float h = clamp( dot(pa,ba)/dot(ba,ba), 0.0, 1. );
	return length( pa - ba*h )*.5;
}

vec3 path(in float i, in float d)
{
    vec3 en = vec3(0.,0.,1.);
    // Reduced amplitude for smoother paths
    float sns2 = sins(d+i*0.5)*0.22*squiggliness;
    float sns = sins(d+i*.6)*0.21*squiggliness;
    en.xz *= mm2((hash(i*10.569)-.5)*6.2+sns2);
    en.xy *= mm2((hash(i*4.732)-.5)*6.2+sns);
    return en;
}

vec2 map(vec3 p, float i)
{
	float lp = length(p);
    vec3 bg = vec3(0.);
    vec3 en = path(i,lp);

    float ins = smoothstep(0.11,.46,lp);
    float outs = .15+smoothstep(.0,.15,abs(lp-1.));
    p *= ins*outs;
    float id = ins*outs;

    float rz = segm(p, bg, en)-0.011;
    return vec2(rz,id);
}

float march(in vec3 ro, in vec3 rd, in float startf, in float maxd, in float j)
{
	float precis = 0.001;
    float h=0.5;
    float d = startf;
    for( int i=0; i<MAX_ITER; i++ )
    {
        if( abs(h)<precis||d>maxd ) break;
        d += h*1.2;
	    float res = map(ro+rd*d, j).x;
        h = res;
    }
	return d;
}

vec3 vmarch(in vec3 ro, in vec3 rd, in float j, in vec3 orig)
{
    vec3 p = ro;
    vec2 r = vec2(0.);
    vec3 sum = vec3(0);
    for( int i=0; i<VOLUMETRIC_STEPS; i++ )
    {
        r = map(p,j);
        p += rd*.03;
        float lp = length(p);

        // Use controllable colors
        vec3 col = mix(plasmaColor1, plasmaColor2, sin(r.y*3.94)*.5+.5);
        col.rgb *= smoothstep(.0,.015,-r.x);
        col *= smoothstep(0.04,.2,abs(lp-1.1));
        col *= smoothstep(0.1,.34,lp);
        sum += abs(col)*5. * (1.2-noise(vec3(lp*2.+j*13.+iTime*speed*5.))) / (log(distance(p,orig)-2.)+.75);
    }
    return sum;
}

vec2 iSphere2(in vec3 ro, in vec3 rd)
{
    vec3 oc = ro;
    float b = dot(oc, rd);
    float c = dot(oc,oc) - 1.;
    float h = b*b - c;
    if(h <0.0) return vec2(-1.);
    else return vec2((-b - sqrt(h)), (-b + sqrt(h)));
}

void mainImage( out vec4 fragColor_out, in vec2 fragCoord )
{
	vec2 p = fragCoord.xy/iResolution.xy-0.5;
	p.x*=iResolution.x/iResolution.y;

	//camera
	vec3 ro = vec3(0.,0.,5.);
    vec3 rd = normalize(vec3(p*.7,-1.5));
    mat2 mx = mm2(iTime*speed*.4*rotationSpeed);
    mat2 my = mm2(iTime*speed*0.3*rotationSpeed);
    ro.xz *= mx;rd.xz *= mx;
    ro.xy *= my;rd.xy *= my;

    vec3 bro = ro;
    vec3 brd = rd;

    vec3 col = vec3(0.0125,0.,0.025);

    for (float j = 1.;j<numRays+1.;j++)
    {
        ro = bro;
        rd = brd;
        mat2 mm = mm2((iTime*speed*0.1+((j+1.)*5.1))*j*0.25);
        ro.xy *= mm;rd.xy *= mm;
        ro.xz *= mm;rd.xz *= mm;
        float rz = march(ro,rd,2.5,FAR,j);
		if ( rz >= FAR)continue;
    	vec3 pos = ro+rz*rd;
    	col = max(col,vmarch(pos,rd,j, bro));
    }

    ro = bro;
    rd = brd;
    vec2 sph = iSphere2(ro,rd);

    if (sph.x > 0.)
    {
        vec3 pos = ro+rd*sph.x;
        vec3 pos2 = ro+rd*sph.y;
        vec3 rf = reflect( rd, pos );
        vec3 rf2 = reflect( rd, pos2 );
        float nz = (-log(abs(flow(rf*1.2,iTime*speed)-.01)));
        float nz2 = (-log(abs(flow(rf2*1.2,-iTime*speed)-.01)));
        col += (0.1*nz*nz* plasmaColor1 + 0.05*nz2*nz2*plasmaColor2)*0.8;
    }

	fragColor_out = vec4(col*1.3*brightness, 1.0);
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
