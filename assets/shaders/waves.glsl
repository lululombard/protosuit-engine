#version 300 es
precision highp float;

// Waves Shader
// Original shader by lululombard
uniform float iTime;
uniform vec2 iResolution;

// Custom uniforms (can be set via MQTT)
// Note: Defaults must be handled in the shader logic, not uniform declarations (GLSL ES 3.0)
uniform float speed;         // Animation speed multiplier
uniform vec3 color1;         // Primary color (orange)
uniform vec3 color2;         // Secondary color (blue)
uniform float intensity;     // Wave intensity
uniform float scale;         // Wave scale

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

void main() {
    vec2 uv = v_fragCoord / iResolution.xy;
    vec2 center = uv - 0.5;

    float r = length(center);
    float a = atan(center.y, center.x);

    // Use custom uniforms
    float time = iTime * speed;
    float wave1 = sin(r * scale - time * 2.0) * intensity;
    float wave2 = sin(a * 8.0 + time) * intensity * 0.5;
    float wave = (wave1 + wave2) * 0.5 + 0.5;

    // Mix colors based on wave pattern
    vec3 col = mix(color1, color2, wave);

    // Add some fade from center
    col *= 1.0 - r * 0.5;

    fragColor = vec4(col, 1.0);
}
