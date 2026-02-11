#version 300 es
precision highp float;

// Audio FFT Visualization
// Based on "Input - Sound" by Inigo Quilez
// https://www.shadertoy.com/view/Xds3Rr

// Standard uniforms
uniform float iTime;
uniform int frame;
uniform vec2 iResolution;

// Audio data texture (512x2, R32F)
// Row 0 (y=0): FFT frequency magnitudes (0.0-1.0)
// Row 1 (y=1): Waveform samples (0.0-1.0, centered at 0.5)
uniform sampler2D iChannel0;

// MQTT-controllable uniforms
uniform float gain;  // Amplitude gain multiplier

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

void mainImage(out vec4 fragColor_out, in vec2 fragCoord) {
    // Create pixel coordinates
    vec2 uv = fragCoord / iResolution.xy;

    // The sound texture is 512x2
    int tx = int(uv.x * 512.0);

    // First row is frequency data (48Khz/4 in 512 texels, meaning 23 Hz per texel)
    float fft = texelFetch(iChannel0, ivec2(tx, 0), 0).x * gain;

    // Second row is the sound wave, one texel is one mono sample
    float wave = texelFetch(iChannel0, ivec2(tx, 1), 0).x;

    // Convert frequency to colors
    vec3 col = vec3(fft, 4.0 * fft * (1.0 - fft), 1.0 - fft) * fft;

    // Add wave form on top
    col += 1.0 - smoothstep(0.0, 0.15, abs(wave - uv.y));

    // Output final color
    fragColor_out = vec4(col, 1.0);
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
