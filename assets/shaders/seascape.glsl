#version 300 es
precision highp float;

/*
 * "Seascape" by Alexander Alekseev aka TDM - 2014
 * License Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported License.
 * Contact: tdmaav@gmail.com
 *
 * Adapted for protosuit-engine with MQTT-controllable parameters
 */

// Standard uniforms
uniform float iTime;
uniform vec2 iResolution;

// MQTT-controllable uniforms
uniform float seaSpeed;        // Animation speed (default: 0.8)
uniform float seaHeight;       // Wave height (default: 0.6)
uniform float seaChoppy;       // Wave choppiness (default: 4.0)
uniform float seaFreq;         // Wave frequency (default: 0.16)
uniform vec3 seaBase;          // Deep water color (default: dark blue)
uniform vec3 seaWater;         // Shallow water color (default: teal/green)
uniform vec3 skyColor;         // Sky tint color (default: orange/sunset)
uniform float cameraHeight;    // Camera Y position (default: 3.5)
uniform float timeScale;       // Overall time multiplier (default: 0.3)

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

const int NUM_STEPS = 32;
const float PI = 3.141592;
const float EPSILON = 1e-3;
#define EPSILON_NRM (0.1 / iResolution.x)

const int ITER_GEOMETRY = 3;
const int ITER_FRAGMENT = 5;
const mat2 octave_m = mat2(1.6,1.2,-1.2,1.6);

// math
mat3 fromEuler(vec3 ang) {
	vec2 a1 = vec2(sin(ang.x),cos(ang.x));
    vec2 a2 = vec2(sin(ang.y),cos(ang.y));
    vec2 a3 = vec2(sin(ang.z),cos(ang.z));
    mat3 m;
    m[0] = vec3(a1.y*a3.y+a1.x*a2.x*a3.x,a1.y*a2.x*a3.x+a3.y*a1.x,-a2.y*a3.x);
	m[1] = vec3(-a2.y*a1.x,a1.y*a2.y,a2.x);
	m[2] = vec3(a3.y*a1.x*a2.x+a1.y*a3.x,a1.x*a3.x-a1.y*a3.y*a2.x,a2.y*a3.y);
	return m;
}

float hash( vec2 p ) {
	float h = dot(p,vec2(127.1,311.7));
    return fract(sin(h)*43758.5453123);
}

float noise( in vec2 p ) {
    vec2 i = floor( p );
    vec2 f = fract( p );
	vec2 u = f*f*(3.0-2.0*f);
    return -1.0+2.0*mix( mix( hash( i + vec2(0.0,0.0) ),
                     hash( i + vec2(1.0,0.0) ), u.x),
                mix( hash( i + vec2(0.0,1.0) ),
                     hash( i + vec2(1.0,1.0) ), u.x), u.y);
}

// lighting
float diffuse(vec3 n,vec3 l,float p) {
    return pow(dot(n,l) * 0.4 + 0.6,p);
}

float specular(vec3 n,vec3 l,vec3 e,float s) {
    float nrm = (s + 8.0) / (PI * 8.0);
    return pow(max(dot(reflect(e,n),l),0.0),s) * nrm;
}

// sky
vec3 getSkyColor(vec3 e) {
    e.y = (max(e.y,0.0)*0.8+0.2)*0.8;
    vec3 baseSky = vec3(pow(1.0-e.y,2.0), 1.0-e.y, 0.6+(1.0-e.y)*0.4) * 1.1;
    return mix(baseSky, skyColor, 0.5);  // Blend with custom sky color
}

// sea
float sea_octave(vec2 uv, float choppy) {
    uv += noise(uv);
    vec2 wv = 1.0-abs(sin(uv));
    vec2 swv = abs(cos(uv));
    wv = mix(wv,swv,wv);
    return pow(1.0-pow(wv.x * wv.y,0.65),choppy);
}

float map(vec3 p, float time) {
    float freq = seaFreq;
    float amp = seaHeight;
    float choppy = seaChoppy;
    vec2 uv = p.xz; uv.x *= 0.75;

    float d, h = 0.0;
    for(int i = 0; i < ITER_GEOMETRY; i++) {
    	d = sea_octave((uv+time)*freq,choppy);
    	d += sea_octave((uv-time)*freq,choppy);
        h += d * amp;
    	uv *= octave_m; freq *= 1.9; amp *= 0.22;
        choppy = mix(choppy,1.0,0.2);
    }
    return p.y - h;
}

float map_detailed(vec3 p, float time) {
    float freq = seaFreq;
    float amp = seaHeight;
    float choppy = seaChoppy;
    vec2 uv = p.xz; uv.x *= 0.75;

    float d, h = 0.0;
    for(int i = 0; i < ITER_FRAGMENT; i++) {
    	d = sea_octave((uv+time)*freq,choppy);
    	d += sea_octave((uv-time)*freq,choppy);
        h += d * amp;
    	uv *= octave_m; freq *= 1.9; amp *= 0.22;
        choppy = mix(choppy,1.0,0.2);
    }
    return p.y - h;
}

vec3 getSeaColor(vec3 p, vec3 n, vec3 l, vec3 eye, vec3 dist) {
    float fresnel = clamp(1.0 - dot(n, -eye), 0.0, 1.0);
    fresnel = min(fresnel * fresnel * fresnel, 0.5);

    vec3 reflected = getSkyColor(reflect(eye, n));
    vec3 refracted = seaBase + diffuse(n, l, 80.0) * seaWater * 0.12;

    vec3 color = mix(refracted, reflected, fresnel);

    float atten = max(1.0 - dot(dist, dist) * 0.001, 0.0);
    color += seaWater * (p.y - seaHeight) * 0.18 * atten;

    color += specular(n, l, eye, 600.0 * inversesqrt(dot(dist,dist)));

    return color;
}

// tracing
vec3 getNormal(vec3 p, float eps, float time) {
    vec3 n;
    n.y = map_detailed(p, time);
    n.x = map_detailed(vec3(p.x+eps,p.y,p.z), time) - n.y;
    n.z = map_detailed(vec3(p.x,p.y,p.z+eps), time) - n.y;
    n.y = eps;
    return normalize(n);
}

float heightMapTracing(vec3 ori, vec3 dir, out vec3 p, float time) {
    float tm = 0.0;
    float tx = 1000.0;
    float hx = map(ori + dir * tx, time);
    if(hx > 0.0) {
        p = ori + dir * tx;
        return tx;
    }
    float hm = map(ori, time);
    for(int i = 0; i < NUM_STEPS; i++) {
        float tmid = mix(tm, tx, hm / (hm - hx));
        p = ori + dir * tmid;
        float hmid = map(p, time);
        if(hmid < 0.0) {
            tx = tmid;
            hx = hmid;
        } else {
            tm = tmid;
            hm = hmid;
        }
        if(abs(hmid) < EPSILON) break;
    }
    return mix(tm, tx, hm / (hm - hx));
}

vec3 getPixel(in vec2 coord, float time) {
    vec2 uv = coord / iResolution.xy;
    uv = uv * 2.0 - 1.0;
    uv.x *= iResolution.x / iResolution.y;

    // ray
    vec3 ang = vec3(sin(time*3.0)*0.1,sin(time)*0.2+0.3,time);
    vec3 ori = vec3(0.0, cameraHeight, time*5.0);
    vec3 dir = normalize(vec3(uv.xy,-2.0)); dir.z += length(uv) * 0.14;
    dir = normalize(dir) * fromEuler(ang);

    // tracing
    float seaTime = 1.0 + iTime * seaSpeed;
    vec3 p;
    heightMapTracing(ori, dir, p, seaTime);
    vec3 dist = p - ori;
    vec3 n = getNormal(p, dot(dist,dist) * EPSILON_NRM, seaTime);
    vec3 light = normalize(vec3(0.0,1.0,0.8));

    // color
    return mix(
        getSkyColor(dir),
        getSeaColor(p,n,light,dir,dist),
    	pow(smoothstep(0.0,-0.02,dir.y),0.2));
}

// main
void mainImage( out vec4 fragColor_out, in vec2 fragCoord ) {
    float time = iTime * timeScale;

    vec3 color = getPixel(fragCoord, time);

    // post
	fragColor_out = vec4(pow(color,vec3(0.65)), 1.0);
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
