#version 300 es
precision highp float;

// Jax Abstraction Shader
// Mirrored psychedelic fractal with rainbow colors
// Created by Guzinh (2025-12-23)
// https://www.shadertoy.com/view/3ccfDl

// Standard uniforms
uniform float iTime;
uniform vec2 iResolution;

// MQTT-controllable uniforms
uniform float speed;          // Animation speed (default: 1.0)
uniform float tunnelSpeed;    // Tunnel travel speed (default: 1.0)
uniform float colorSpeed;     // Color cycling speed (default: 0.1)
uniform float glowIntensity;  // Glow/fog intensity (default: 1.0)
uniform float corridorWidth;  // Width of central corridor (default: 2.0)
uniform float gamma;          // Gamma correction (default: 0.6)

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

// 2D rotation
mat2 rot(float a) {
    float s = sin(a), c = cos(a);
    return mat2(c, -s, s, c);
}

// Rainbow palette function (Inigo Quilez technique)
vec3 palette(float t) {
    vec3 a = vec3(0.5, 0.5, 0.5);
    vec3 b = vec3(0.5, 0.5, 0.5);
    vec3 c = vec3(1.0, 1.0, 1.0);
    vec3 d = vec3(0.0, 0.33, 0.67);
    return a + b * cos(6.28318 * (c * t + d));
}

// Fractal shape
float fractal(vec3 p) {
    float s = 1.0;
    for (int i = 0; i < 5; i++) {
        p.xy *= rot(0.1);
        p.yz *= rot(0.55 + float(i) * 0.47);
        p = abs(p) - vec3(0.8, 1.0, 0.9);
        float d = dot(p, p);
        float k = 2.0 / max(d, 0.5);
        p *= k;
        s *= k;
    }
    return (length(p.xz) - 0.55) / s;
}

// World map
float map(vec3 p) {
    float time = iTime * speed;
    float zRepeat = 10.0;
    p.z += time * tunnelSpeed;
    p.z = mod(p.z, zRepeat) - zRepeat * 0.5;

    p.xy *= rot(p.z * (0.22 + cos(time / 5.0) / 10.0));

    vec3 q = p;

    // Mirror symmetry with central corridor
    q.x = abs(q.x) - corridorWidth + cos(time / 15.0);

    float d = fractal(q);
    d = max(d, -q.x - 0.3);

    return d;
}

void mainImage(out vec4 fragColor_out, in vec2 fragCoord) {
    vec2 uv = (fragCoord - 0.5 * iResolution.xy) / iResolution.y;
    float time = iTime * speed;

    vec3 ro = vec3(0.0, 0.0, -1.0);
    vec3 rd = normalize(vec3(uv, 1.0));

    float colorTime = time * colorSpeed;
    vec3 colStruct = palette(colorTime);
    vec3 colGlow = palette(colorTime + 0.3);

    float t = 0.0;
    float d = 0.0;
    vec3 p = vec3(0.0);
    vec3 finalColor = vec3(0.0);
    float glowAccum = 0.0;

    // Raymarching loop
    for (int i = 0; i < 100; i++) {
        p = ro + rd * t;
        d = map(p);

        float localGlow = exp(-d * 3.0);
        glowAccum += localGlow * (0.015 + 0.01 * sin(t + time));

        t += d * 0.5;

        if (d < 0.002 || t > 50.0) break;
    }

    // Add accumulated glow
    finalColor += glowAccum * colGlow * 2.0 * glowIntensity;

    // Structure hit
    if (d < 0.01) {
        float fog = 1.0 / (1.0 + t * t * 0.05);
        vec3 structureColor = colStruct * fog;
        finalColor = mix(finalColor, structureColor, 0.7);
    }

    // Final adjustments
    finalColor = pow(finalColor, vec3(gamma));
    finalColor *= 1.2 - length(uv) * 0.5; // Vignette

    fragColor_out = vec4(finalColor, 1.0);
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
