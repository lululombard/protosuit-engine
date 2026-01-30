#version 300 es
precision highp float;

// Optical Lens Shader
// Created by Danguafer/Danilo Guanabara (2014-04-29)
// https://www.shadertoy.com/view/XsXXDn

// Standard uniforms
uniform float iTime;
uniform vec2 iResolution;

// MQTT-controllable uniforms
uniform float speed;        // Animation speed (default: 1.0)
uniform float intensity;    // Effect intensity (default: 1.0)
uniform float scale;        // Pattern scale (default: 9.0)
uniform vec3 lensColor;     // Lens color tint (default: white)

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

#define t iTime
#define r iResolution.xy

void mainImage( out vec4 fragColor_out, in vec2 fragCoord ){
	vec3 c;
	float l,z=t * speed;
	for(int i=0;i<3;i++) {
		vec2 uv,p=fragCoord.xy/r;
		uv=p;
		p-=.5;
		p.x*=r.x/r.y;
		z+=.07;
		l=length(p);
		uv+=p/l*(sin(z)+1.)*abs(sin(l*scale-z-z));
		c[i]=.01/length(mod(uv,1.)-.5) * intensity;
	}
	fragColor_out=vec4(c/l * lensColor, 1.0);
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
