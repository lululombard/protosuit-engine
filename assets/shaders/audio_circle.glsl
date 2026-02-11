#version 300 es
precision highp float;

// Circular Audio Visualizer
// Radial FFT bars + waveform ring, designed for round displays

// Standard uniforms
uniform float iTime;
uniform int frame;
uniform vec2 iResolution;

// Audio data texture (512x2, R32F)
uniform sampler2D iChannel0;

// MQTT-controllable uniforms
uniform float gain;
uniform float speed;
uniform float ringRadius;
uniform float barLength;
uniform float glowIntensity;

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

vec3 hsl2rgb(float h, float s, float l) {
    vec3 rgb = clamp(abs(mod(h * 6.0 + vec3(0.0, 4.0, 2.0), 6.0) - 3.0) - 1.0, 0.0, 1.0);
    return l + s * (rgb - 0.5) * (1.0 - abs(2.0 * l - 1.0));
}

void mainImage(out vec4 fragColor_out, in vec2 fragCoord) {
    vec2 uv = (fragCoord - 0.5 * iResolution.xy) / min(iResolution.x, iResolution.y);
    float dist = length(uv);
    float angle = atan(uv.y, uv.x);

    // Circular display mask
    float mask = smoothstep(0.5, 0.49, dist);
    if (mask < 0.001) {
        fragColor_out = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    // Map angle to texture coordinate (0-1)
    float t = (angle + 3.14159) / (2.0 * 3.14159);

    // Sample FFT and waveform
    int tx = int(t * 512.0);
    float fft = texelFetch(iChannel0, ivec2(tx, 0), 0).x * gain;
    float wave = texelFetch(iChannel0, ivec2(tx, 1), 0).x;
    wave = (wave - 0.5) * 2.0;

    // Background: dark with subtle radial gradient
    vec3 col = vec3(0.02, 0.02, 0.04) * (1.0 - dist * 0.5);

    // --- Radial FFT bars ---
    float innerR = ringRadius;
    float outerR = innerR + fft * barLength;
    float barDist = smoothstep(innerR - 0.005, innerR, dist) *
                    smoothstep(outerR + 0.005, outerR, dist);

    // Color by frequency position, shift hue over time
    float hue = t + iTime * speed * 0.05;
    vec3 barColor = hsl2rgb(hue, 0.85, 0.4 + 0.3 * fft);

    col += barColor * barDist;

    // Glow around bars
    float glowOuter = smoothstep(outerR + 0.08 * glowIntensity, outerR, dist);
    float glowInner = smoothstep(innerR - 0.04 * glowIntensity, innerR, dist);
    col += barColor * glowOuter * glowInner * fft * 0.4 * glowIntensity;

    // --- Waveform ring ---
    float waveR = ringRadius * 0.55 + wave * 0.06;
    float waveDist = abs(dist - waveR);
    float waveIntensity = smoothstep(0.012, 0.0, waveDist);

    vec3 waveColor = hsl2rgb(iTime * speed * 0.1 + dist, 0.9, 0.6);
    col += waveColor * waveIntensity;

    // Glow on waveform
    float waveGlow = smoothstep(0.05 * glowIntensity, 0.0, waveDist);
    col += waveColor * waveGlow * 0.15 * glowIntensity;

    // --- Center dot pulse ---
    float bass = texelFetch(iChannel0, ivec2(5, 0), 0).x * gain;
    float pulse = smoothstep(0.06 + bass * 0.04, 0.0, dist);
    vec3 pulseColor = hsl2rgb(iTime * speed * 0.15, 1.0, 0.5);
    col += pulseColor * pulse * 0.8;

    // Apply circular mask
    col *= mask;

    fragColor_out = vec4(col, 1.0);
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
