#version 300 es
precision highp float;

// Hypnosis Tunnel Shader
// Created by s23b (2016-01-11)
// https://www.shadertoy.com/view/4st3WX

// Standard uniforms
uniform float iTime;
uniform vec2 iResolution;

// MQTT-controllable uniforms
uniform float speed;          // Animation speed (default: 1.0)
uniform float intensity;      // Tunnel depth/intensity (default: 1.0)
uniform float darkness;       // Edge darkness, 0=bright 2=dark (default: 0.0)
uniform vec3 tunnelColor;     // Tunnel foreground color (default: white)
uniform vec3 backgroundColor; // Background/black part color (default: black)

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

#define PI 3.14159265359

void mainImage( out vec4 fragColor_out, in vec2 fragCoord )
{
	vec2 uv = fragCoord.xy / iResolution.xy / .5 - 1.;
    uv.x *= iResolution.x / iResolution.y;

    // make a tube
    float f = 1. / length(uv) * intensity;

    // add the angle
    f += atan(uv.x, uv.y) / acos(0.);

    // let's roll
    f -= iTime * speed;

    // make it black and white
    // old version without AA: f = floor(fract(f) * 2.);
    // new version with AA:
   	f = 1. - clamp(sin(f * PI * 2.) * dot(uv, uv) * iResolution.y / 15. + .5, 0., 1.);

    // add the darkness to the end of the tunnel (inverted so higher = darker)
    f *= sin(length(uv) - .1) * (1.0 - darkness);

    // mix between background color and tunnel color
    vec3 finalColor = mix(backgroundColor, tunnelColor, f);
    fragColor_out = vec4(finalColor, 1.0);
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
