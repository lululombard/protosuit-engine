#version 300 es
precision highp float;

// Standard uniforms
uniform float iTime;
uniform vec2 iResolution;

// MQTT-controllable uniforms
uniform float rotationSpeed;    // Rotation speed (default: 1.0)
uniform float baguetteSize;     // Baguette size (default: 0.3)

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

const float PI = 3.14159265;

// French flag colors
const vec3 BLEU = vec3(0.0, 0.15, 0.5);
const vec3 BLANC = vec3(1.0, 1.0, 1.0);
const vec3 ROUGE = vec3(0.9, 0.1, 0.15);

// Baguette colors
const vec3 CROUTE = vec3(0.76, 0.53, 0.26);
const vec3 CROUTE_DARK = vec3(0.55, 0.35, 0.15);

// 2D rotation matrix
mat2 rotate2d(float angle) {
    float c = cos(angle);
    float s = sin(angle);
    return mat2(c, -s, s, c);
}

// Rounded box SDF
float sdRoundedBox(vec2 p, vec2 b, float r) {
    vec2 q = abs(p) - b + r;
    return min(max(q.x, q.y), 0.0) + length(max(q, 0.0)) - r;
}

// Baguette SDF (elongated rounded shape with scoring)
float sdBaguette(vec2 p, float size) {
    // Main baguette body
    float body = sdRoundedBox(p, vec2(size * 2.0, size * 0.35), size * 0.3);
    return body;
}

// Baguette scoring lines
float baguetteScoring(vec2 p, float size) {
    float score = 0.0;
    for (int i = -3; i <= 3; i++) {
        vec2 offset = vec2(float(i) * size * 0.5, 0.0);
        vec2 rotated = rotate2d(0.5) * (p - offset);
        float line = sdRoundedBox(rotated, vec2(size * 0.25, size * 0.03), 0.01);
        score = max(score, 1.0 - smoothstep(0.0, 0.02, line));
    }
    return score;
}

void main() {
    vec2 uv = v_fragCoord / iResolution;
    vec2 centered = (v_fragCoord - iResolution * 0.5) / min(iResolution.x, iResolution.y);

    // French flag background
    vec3 flag;
    if (uv.x < 0.333) {
        flag = BLEU;
    } else if (uv.x < 0.666) {
        flag = BLANC;
    } else {
        flag = ROUGE;
    }

    // Rotate baguette
    float angle = iTime * rotationSpeed;
    vec2 rotatedUV = rotate2d(angle) * centered;

    // Draw baguette
    float size = baguetteSize;
    float dist = sdBaguette(rotatedUV, size);

    // Baguette color with shading
    vec3 baguetteColor = CROUTE;

    // Add scoring marks (darker lines)
    float scoring = baguetteScoring(rotatedUV, size);
    baguetteColor = mix(baguetteColor, CROUTE_DARK, scoring * 0.7);

    // Add subtle gradient for 3D effect
    float gradient = dot(rotatedUV, vec2(0.5, 0.5)) * 0.5 + 0.5;
    baguetteColor = mix(CROUTE_DARK, baguetteColor, gradient);

    // Composite
    float baguetteMask = 1.0 - smoothstep(-0.01, 0.01, dist);
    vec3 color = mix(flag, baguetteColor, baguetteMask);

    // Subtle outline
    float outline = smoothstep(0.01, 0.02, abs(dist)) * (1.0 - smoothstep(-0.02, 0.0, dist));
    color = mix(color, CROUTE_DARK * 0.5, outline * 0.5);

    fragColor = vec4(color, 1.0);
}