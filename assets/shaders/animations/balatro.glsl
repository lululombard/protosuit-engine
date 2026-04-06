#version 300 es
precision highp float;

// Balatro Shader
// Original by localthunk (https://www.playbalatro.com)
// Shadertoy version by xxidbr9 (2025-01-14)
// https://www.shadertoy.com/view/XXtBRr

// Standard uniforms
uniform float iTime;
uniform vec2 iResolution;

// MQTT-controllable uniforms
uniform float spinRotation;   // Spin rotation amount (default: -2.0)
uniform float spinSpeed;      // Animation speed (default: 7.0)
uniform float spinAmount;     // Spiral distortion amount (default: 0.25)
uniform float spinEase;       // Spin easing (default: 1.0)
uniform float contrast;       // Color contrast (default: 3.5)
uniform float lighting;       // Lighting intensity (default: 0.4)
uniform float pixelFilter;    // Pixel size filter (default: 745.0)
uniform vec3 color1;          // Primary color (default: red)
uniform vec3 color2;          // Secondary color (default: blue)
uniform vec3 color3;          // Background color (default: dark)
uniform float isRotate;       // Enable rotation (default: 0.0 = false)

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

#define PI 3.14159265359

vec4 effect(vec2 screenSize, vec2 screen_coords) {
    float pixel_size = length(screenSize.xy) / pixelFilter;
    vec2 uv = (floor(screen_coords.xy * (1.0 / pixel_size)) * pixel_size - 0.5 * screenSize.xy) / length(screenSize.xy);
    float uv_len = length(uv);

    float speed = (spinRotation * spinEase * 0.2);
    if (isRotate > 0.5) {
        speed = iTime * speed;
    }
    speed += 302.2;
    float new_pixel_angle = atan(uv.y, uv.x) + speed - spinEase * 20.0 * (1.0 * spinAmount * uv_len + (1.0 - 1.0 * spinAmount));
    vec2 mid = (screenSize.xy / length(screenSize.xy)) / 2.0;
    uv = (vec2((uv_len * cos(new_pixel_angle) + mid.x), (uv_len * sin(new_pixel_angle) + mid.y)) - mid);

    uv *= 30.0;
    speed = iTime * spinSpeed;
    vec2 uv2 = vec2(uv.x + uv.y);

    for (int i = 0; i < 5; i++) {
        uv2 += sin(max(uv.x, uv.y)) + uv;
        uv  += 0.5 * vec2(cos(5.1123314 + 0.353 * uv2.y + speed * 0.131121), sin(uv2.x - 0.113 * speed));
        uv  -= 1.0 * cos(uv.x + uv.y) - 1.0 * sin(uv.x * 0.711 - uv.y);
    }

    float contrast_mod = (0.25 * contrast + 0.5 * spinAmount + 1.2);
    float paint_res = min(2.0, max(0.0, length(uv) * 0.035 * contrast_mod));
    float c1p = max(0.0, 1.0 - contrast_mod * abs(1.0 - paint_res));
    float c2p = max(0.0, 1.0 - contrast_mod * abs(paint_res));
    float c3p = 1.0 - min(1.0, c1p + c2p);
    float light = (lighting - 0.2) * max(c1p * 5.0 - 4.0, 0.0) + lighting * max(c2p * 5.0 - 4.0, 0.0);

    vec4 col1 = vec4(color1, 1.0);
    vec4 col2 = vec4(color2, 1.0);
    vec4 col3 = vec4(color3, 1.0);

    return (0.3 / contrast) * col1 + (1.0 - 0.3 / contrast) * (col1 * c1p + col2 * c2p + vec4(c3p * col3.rgb, c3p * col1.a)) + light;
}

void mainImage(out vec4 fragColor_out, in vec2 fragCoord) {
    vec2 uv = fragCoord / iResolution.xy;
    fragColor_out = effect(iResolution.xy, uv * iResolution.xy);
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
