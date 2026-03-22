#version 300 es
precision highp float;

// Monster Shader - Fractal Tunnel
// Created by butadiene (2020-03-05)
// https://www.shadertoy.com/view/WtKSzt

// Standard uniforms
uniform float iTime;
uniform vec2 iResolution;

// MQTT-controllable uniforms
uniform float speed;           // Movement speed (default: 1.0)
uniform float rotationSpeed;   // Rotation speed (default: 1.0)
uniform float iterations;      // Fractal iterations (default: 4.0)
uniform vec3 tunnelColor;      // Main tunnel color (default: cyan)
uniform vec3 glowColor;        // Glow/emission color (default: green)
uniform float glowIntensity;   // Glow intensity (default: 3.0)
uniform float brightness;      // Overall brightness (default: 1.0)

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

float TK = 1.;
float PI = 3.1415926535;

vec2 rot(vec2 p,float r){
	mat2 m = mat2(cos(r),sin(r),-sin(r),cos(r));
	return m*p;
}

vec2 pmod(vec2 p,float n){
	float np = 2.0*PI/n;
	float r = atan(p.x,p.y)-0.5*np;
	r = mod(r,np)-0.5*np;
	return length(p)*vec2(cos(r),sin(r));
}

float cube(vec3 p,vec3 s){
	vec3 q = abs(p);
	vec3 m = max(s-q,0.0);
	return length(max(q-s,0.0))-min(min(m.x,m.y),m.z);
}

float dist(vec3 p){
	p.z -= 1.*TK*iTime*speed;
	p.xy = rot(p.xy,1.0*p.z*rotationSpeed);
	p.xy = pmod(p.xy,6.0);
	float k = 0.7;
	float zid = floor(p.z*k);
	p = mod(p,k)-0.5*k;
	int maxIter = int(iterations);
	for(int i = 0;i<10;i++){
		if(i >= maxIter) break;
		p = abs(p)-0.3;

		p.xy = rot(p.xy,1.0+zid+0.1*TK*iTime*rotationSpeed);
		p.xz = rot(p.xz,1.0+4.7*zid+0.3*TK*iTime*rotationSpeed);
	}
	return min(cube(p,vec3(0.3)),length(p)-0.4);
}


void mainImage( out vec4 fragColor_out, in vec2 fragCoord )
{
    vec2 uv = fragCoord/iResolution.xy;
	uv = 2.0*(uv-0.5);
	uv.y *= iResolution.y/iResolution.x;
	uv = rot(uv,TK*iTime*rotationSpeed);
	vec3 ro = vec3(0.0,0.0,0.1);
	vec3 rd = normalize(vec3(uv,0.0)-ro);
	float t  =2.0;
	float d = 0.0;
	float ac = 0.0;
	for(int i = 0;i<66;i++){
		d = dist(ro+rd*t)*0.2;
		d = max(0.0000,abs(d));
		t += d;
		if(d<0.001)ac += 0.1;
	}
	vec3 col = vec3(0.0);
	col = tunnelColor*0.2*vec3(ac);
	vec3 pn = ro+rd*t;
	float kn = 0.5;
	pn.z += -1.5*iTime*TK*speed;
	pn.z = mod(pn.z,kn)-0.5*kn;
	float em = clamp(0.01/pn.z,0.0,100.0);
	col += glowIntensity*em*glowColor;
	col = clamp(col,0.0,1.0);
	col *= brightness;

    fragColor_out = vec4(col,1.0);
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
