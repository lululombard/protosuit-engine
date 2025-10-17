#version 300 es
precision highp float;

// Created by Danil (2024+) https://github.com/danilw
// License - CC0 or use as you wish
// Original: https://www.shadertoy.com/view/MXl3WX

// Converted to moderngl format for protosuit-engine

// Uniforms from moderngl
uniform float iTime;
uniform vec2 iResolution;

// Custom uniforms for interactive control
uniform vec3 portalOrange;     // Orange portal color (0.0-1.0)
uniform vec3 portalBlue;       // Blue portal color (0.0-1.0)
uniform float portalSpeed;     // Speed multiplier (0.1-3.0)
uniform float portalIntensity; // Overall brightness/intensity (0.1-2.0)
uniform float portalGlow;      // Glow effect strength (0.0-2.0)
uniform float portalSize;      // Portal size/scale (0.5-2.0)

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

// change show define
// 0 particles
// 1 blured lines
#define show 1

// sdf scale
const float line = 0.003;
const float px = 0.004;

// Use uniforms instead of hardcoded colors
// #define PORTAL_ORANGE vec3(1.000,0.5,0.000)
// #define PORTAL_BLUE vec3(0.0,0.5,1.0)

#define MD(a) mat2(cos(a), -sin(a), sin(a), cos(a))
#define PI 3.14159265358979

float hash11(float p);
float sdEllipse( in vec2 p, in vec2 ab );

float draw(vec2 p, float px, float timer){
    const int ldraw = 15;
    const int lstep = 10;

    float d = sdEllipse(p, vec2(0.35,0.45) * portalSize);

    int lid = int((d+(line+px*2.)*0.5)/(line+px*2.));
    lid+=lstep*int(d<-(line+px*2.)*0.5);
    lid+=(lstep+1)*int(d>-(line+px*2.)*0.5);
    d = mod(abs(d),line+px*2.)-(line+px*2.)*0.5;
    d = smoothstep(-px,px,abs(d));

    d = d*step(0.,float(lid))*step(float(lid),float(ldraw));

    lid+=2;
    float rot = timer*(0.25+(float(lid)+5.77*hash11(float(lid)*15.457))*0.45)+float(lid)*PI*0.23;
#if(show)
    rot*=2.;
    rot+=(3.+float(lid)*.75)*sin(timer*0.733+float(lid)*PI*0.35);
    vec2 tp = (p*MD(rot*0.5));
    float td = smoothstep(0.,px,tp.x);
#else
    rot*=.65;
    vec2 tp = (p*MD(rot*0.5));
    float td = smoothstep(0.,px,tp.x*sign(tp.y))*(smoothstep(0.,0.005+0.063*clamp(float(lid-7)/20.,0.,1.),abs(tp.y)));
#endif
    td*=1.-smoothstep(0.,0.25+0.015*float(abs(lid)),abs(tp.y));
    d*=td;

    return d;
}

void mainImage( out vec4 fragColor_out, in vec2 fragCoord )
{
    vec2 res = iResolution.xy/iResolution.y;
    vec2 uv = fragCoord/iResolution.y-0.5*res;

    float time = iTime * portalSpeed;

    float d = draw(uv,px, time);
    float d2 = draw(uv,px, time*1.33+1.5);
    float d3 = draw(uv*1.015,px*1.015, time);
    float d4 = draw(uv*1.015,px*1.015, time*1.33+1.5);

    float db = draw(uv,px, time*1.5+5.);
    float db2 = draw(uv,px, time*1.5*1.33+1.5+5.);
    float db3 = draw(uv*1.015,px*1.015, time*1.5+5.);
    float db4 = draw(uv*1.015,px*1.015, time*1.5*1.33+1.5+5.);

    float dr = clamp((d3*d4+d*d2),0.,1.);
    float dbr = clamp((db3*db4+db*db2),0.,1.);

    vec3 ca = portalOrange*dr;
    vec3 cb = portalBlue*dbr;

    vec3 c = ca+cb;

    c = c+0.65*pow(c,vec3(2.2)) * portalIntensity;

    float ed = abs(sdEllipse(uv, 0.85*vec2(0.35,0.45) * portalSize));
    c*=1.-smoothstep(0.025,0.175,ed);
    float g = 1.-smoothstep(-0.1,0.25,ed);
    g*=0.75 * portalGlow;
    vec3 tc = 0.5+0.5*cos(time*0.75+uv.xyx*0.5+vec3(0,2,4));
    c+=g*g*(mix(portalBlue,portalOrange,tc.r)+tc*0.5)+g*g*(portalBlue*d*db2+portalOrange*d3*db4);

    fragColor_out = vec4(c,1.0);
}

float sdEllipse( in vec2 p, in vec2 ab )
{
    p = abs(p); if( p.x > p.y ) {p=p.yx;ab=ab.yx;}
    float l = ab.y*ab.y - ab.x*ab.x;
    float m = ab.x*p.x/l;      float m2 = m*m;
    float n = ab.y*p.y/l;      float n2 = n*n;
    float c = (m2+n2-1.0)/3.0; float c3 = c*c*c;
    float q = c3 + m2*n2*2.0;
    float d = c3 + m2*n2;
    float g = m + m*n2;
    float co;
    if( d<0.0 )
    {
        float h = acos(q/c3)/3.0;
        float s = cos(h);
        float t = sin(h)*sqrt(3.0);
        float rx = sqrt( -c*(s + t + 2.0) + m2 );
        float ry = sqrt( -c*(s - t + 2.0) + m2 );
        co = (ry+sign(l)*rx+abs(g)/(rx*ry)- m)/2.0;
    }
    else
    {
        float h = 2.0*m*n*sqrt( d );
        float s = sign(q+h)*pow(abs(q+h), 1.0/3.0);
        float u = sign(q-h)*pow(abs(q-h), 1.0/3.0);
        float rx = -s - u - c*4.0 + 2.0*m2;
        float ry = (s - u)*sqrt(3.0);
        float rm = sqrt( rx*rx + ry*ry );
        co = (ry/sqrt(rm-rx)+2.0*g/rm-m)/2.0;
    }
    vec2 r = ab * vec2(co, sqrt(1.0-co*co));
    return length(r-p) * sign(p.y-r.y);
}

float hash11(float p)
{
    p = fract(p * .1031);
    p *= p + 33.33;
    p *= p + p;
    return fract(p);
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
