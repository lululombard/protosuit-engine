#version 300 es
precision highp float;

// Fractal Land Shader
// Created by Kali (2013-11-07)
// https://www.shadertoy.com/view/XsBXWt

// Standard uniforms
uniform float iTime;
uniform vec2 iResolution;

// MQTT-controllable uniforms
uniform float speed;          // Animation speed (default: 1.0)
uniform float edgeIntensity;  // Edge detection intensity (default: 1.0)
uniform float sunSize;        // Sun size (default: 7.0)
uniform vec3 skyColor;        // Sky color (default: purple)
uniform vec3 sunColor;        // Sun color (default: yellow)
uniform vec3 landColor;       // Land/terrain color (default: yellow-white)
uniform float brightness;     // Overall brightness (default: 1.2)
uniform float waves;          // Enable waves (default: 1.0, 0.0=off)

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

#define RAY_STEPS 150
#define GAMMA 1.4
#define SATURATION .65
#define detail .001

float det=0.0;
float edge=0.;

// 2D rotation function
mat2 rot(float a) {
	return mat2(cos(a),sin(a),-sin(a),cos(a));
}

// "Amazing Surface" fractal
vec4 formula(vec4 p) {
	p.xz = abs(p.xz+1.)-abs(p.xz-1.)-p.xz;
	p.y-=.25;
	p.xy*=rot(radians(35.));
	p=p*2./clamp(dot(p.xyz,p.xyz),.2,1.);
	return p;
}

// Distance function
float de(vec3 pos) {
	float t = iTime * speed * .5;
	if (waves > 0.5) {
		pos.y+=sin(pos.z-t*6.)*.15; //waves!
	}
	vec3 tpos=pos;
	tpos.z=abs(3.-mod(tpos.z,6.));
	vec4 p=vec4(tpos,1.);
	for (int i=0; i<4; i++) {p=formula(p);}
	float fr=(length(max(vec2(0.),p.yz-1.5))-1.)/p.w;
	float ro=max(abs(pos.x+1.)-.3,pos.y-.35);
	ro=max(ro,-max(abs(pos.x+1.)-.1,pos.y-.5));
	pos.z=abs(.25-mod(pos.z,.5));
	ro=max(ro,-max(abs(pos.z)-.2,pos.y-.3));
	ro=max(ro,-max(abs(pos.z)-.01,-pos.y+.32));
	float d=min(fr,ro);
	return d;
}

// Camera path
vec3 path(float ti) {
	ti*=1.5;
	vec3 p=vec3(sin(ti),(1.-sin(ti*2.))*.5,-ti*5.)*.5;
	return p;
}

// Calc normals and edge detection
vec3 normal(vec3 p) {
	vec3 e = vec3(0.0,det*5.,0.0);
	float d1=de(p-e.yxx),d2=de(p+e.yxx);
	float d3=de(p-e.xyx),d4=de(p+e.xyx);
	float d5=de(p-e.xxy),d6=de(p+e.xxy);
	float d=de(p);
	edge=abs(d-0.5*(d2+d1))+abs(d-0.5*(d4+d3))+abs(d-0.5*(d6+d5));
	edge=min(1.,pow(edge,.55)*15.*edgeIntensity);
	return normalize(vec3(d1-d2,d3-d4,d5-d6));
}

// Raymarching
vec3 raymarch(in vec3 from, in vec3 dir)
{
	float t = iTime * speed * .5;
	edge=0.;
	vec3 p, norm;
	float d=100.;
	float totdist=0.;
	for (int i=0; i<RAY_STEPS; i++) {
		if (d>det && totdist<25.0) {
			p=from+totdist*dir;
			d=de(p);
			det=detail*exp(.13*totdist);
			totdist+=d;
		}
	}
	vec3 col=vec3(0.);
	p-=(det-d)*dir;
	norm=normal(p);
	col=(1.-abs(norm))*max(0.,1.-edge*.8)*landColor;

	totdist=clamp(totdist,0.,26.);
	dir.y-=.02;

	// Procedural sun size variation
	float sunVariation = sin(t * 2.0) * 0.5 + 0.5;
	float effectiveSunSize = sunSize - sunVariation * 2.0;
	float an=atan(dir.x,dir.y)+t*3.; // angle for drawing and rotating sun
	float s=pow(clamp(1.0-length(dir.xy)*effectiveSunSize-abs(.2-mod(an,.4)),0.,1.),.1); // sun
	float sb=pow(clamp(1.0-length(dir.xy)*(effectiveSunSize-.2)-abs(.2-mod(an,.4)),0.,1.),.1); // sun border
	float sg=pow(clamp(1.0-length(dir.xy)*(effectiveSunSize-4.5)-.5*abs(.2-mod(an,.4)),0.,1.),3.); // sun rays
	float y=mix(.45,1.2,pow(smoothstep(0.,1.,.75-dir.y),2.))*(1.-sb*.5); // gradient sky

	// Background with sky and sun
	vec3 backg=skyColor*((1.-s)*(1.-sg)*y+(1.-sb)*sg*sunColor*3.);
	backg+=sunColor*s;
	backg=max(backg,sg*sunColor);

	col=mix(sunColor*.8,col,exp(-.004*totdist*totdist)); // distant fading to sun color
	if (totdist>25.) col=backg; // hit background
	col=pow(col,vec3(GAMMA))*brightness;
	col=mix(vec3(length(col)),col,SATURATION);
	col*=vec3(1.,.9,.85);

	return col;
}

// Get camera position
vec3 move(inout vec3 dir) {
	float t = iTime * speed * .5;
	vec3 go=path(t);
	vec3 adv=path(t+.7);
	vec3 advec=normalize(adv-go);
	float an=adv.x-go.x;
	an*=min(1.,abs(adv.z-go.z))*sign(adv.z-go.z)*.7;
	dir.xy*=mat2(cos(an),sin(an),-sin(an),cos(an));
	an=advec.y*1.7;
	dir.yz*=mat2(cos(an),sin(an),-sin(an),cos(an));
	an=atan(advec.x,advec.z);
	dir.xz*=mat2(cos(an),sin(an),-sin(an),cos(an));
	return go;
}

void mainImage( out vec4 fragColor_out, in vec2 fragCoord )
{
	vec2 uv = fragCoord.xy / iResolution.xy*2.-1.;
	vec2 oriuv=uv;
	uv.y*=iResolution.y/iResolution.x;

	float fov=.9-max(0.,.7-iTime*speed*.3*.15);
	vec3 dir=normalize(vec3(uv*fov,1.));

	vec3 origin=vec3(-1.,.7,0.);
	vec3 from=origin+move(dir);
	vec3 color=raymarch(from,dir);

	// Border vignette
	color=mix(vec3(0.),color,pow(max(0.,.95-length(oriuv*oriuv*oriuv*vec2(1.05,1.1))),.3));

	fragColor_out = vec4(color,1.);
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
