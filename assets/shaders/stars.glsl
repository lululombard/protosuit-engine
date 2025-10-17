#version 300 es
precision highp float;

// Standard uniforms
uniform float iTime;
uniform int frame;
uniform vec2 iResolution;

// MQTT-controllable uniforms
uniform float speed;        // Animation speed multiplier (can be negative to reverse)
uniform float mirrorX;      // Mirror horizontally: 1.0 = normal, -1.0 = mirrored
uniform vec3 color1;        // Primary color (default: white)
uniform vec3 color2;        // Secondary color (default: gray)
uniform vec3 accentColor;   // Accent color for some stars (default: black)

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

// Persona 5 Style Starfield Animation (Unified & Controllable)
// Adapted from Shadertoy "Persona 5 menu background" by soilmaster
// https://www.shadertoy.com/view/sd2BWy

// Math constants
#define M_PI     3.141592
#define RAD2DEG  (M_PI / 360.0 * 2.0)
#define DEG2RAD  (360.0 / M_PI / 2.0)

// 5-pointed star SDF (Signed Distance Function)
float sdfStar5(in vec2 p)
{
    // Repeat domain 5x for star symmetry
    const vec2 k1 = vec2(0.809016994375, -0.587785252292);
    const vec2 k2 = vec2(-k1.x, k1.y);

    p.x = abs(p.x);
    p -= 2.0 * max(dot(k1, p), 0.0) * k1;
    p -= 2.0 * max(dot(k2, p), 0.0) * k2;

    const vec2 k3 = vec2(0.951056516295, 0.309016994375);
    return dot(vec2(abs(p.x) - 0.3, p.y), k3);
}

// Smooth square wave function for animation
float smoothSquareWave(float a, float blur)
{
    a = a - floor(a);
    if (a <= 0.25) return smoothstep(-blur, blur, a);
    if (a >= 0.75) return smoothstep(1.0 - blur, 1.0 + blur, a);
    return 1.0 - smoothstep(0.5 - blur, 0.5 + blur, a);
}

// 2D rotation matrix
mat2 rotate2d(float angle)
{
    return mat2(cos(angle), -sin(angle),
                sin(angle),  cos(angle));
}

// 2D scaling matrix
mat2 scale2d(float scale)
{
    return mat2(scale, 0.0,
                0.0,   scale);
}

// Persona-style animated star
vec4 personaStar(
    vec2 fragCoord,
    vec2 position,
    float angle,
    float size,
    vec3 col1,
    vec3 col2,
    float rippleDir,
    float globalPixelWidth,
    float time)
{
    fragCoord = rotate2d(DEG2RAD * angle) * (fragCoord - position);
    fragCoord = scale2d(size) * fragCoord;
    float starPixelWidth = globalPixelWidth * size * 7.0;

    float dist = sdfStar5(fragCoord);

    vec4 col;
    col = vec4(mix(col1, col2, smoothSquareWave(dist * 9.0 + 0.4 * time * rippleDir, starPixelWidth)), 1.0);
    col.a = 1.0 - smoothstep(0.0, globalPixelWidth * 2.0, dist);

    return col;
}

// Blend color with existing color using alpha
void applyColor(inout vec3 existingColor, vec4 inputColor)
{
    existingColor = mix(existingColor.xyz, inputColor.xyz, inputColor.a);
}

void main() {
    vec2 HOOKED_pos = v_fragCoord / iResolution;
    vec2 fragCoord = HOOKED_pos * iResolution;

    // Normalize coordinates with aspect ratio correction
    vec2 p = (2.0 * fragCoord - iResolution.xy) / iResolution.y;

    // Apply horizontal mirroring
    p.x *= mirrorX;

    float pw = 2.0 / iResolution.y;
    vec3 col = color1;

    // Apply speed multiplier to time (speed can be negative to reverse)
    float animTime = iTime * speed;

    // Render stars with varied ripple directions for visual interest
    applyColor(col, personaStar(p, vec2(-0.628, 0.903), 232.285, 0.401, color1, color2, -1.0, pw, animTime));
    applyColor(col, personaStar(p, vec2(0.363, -0.717), 202.978, 0.550, color1, color2, -1.0, pw, animTime));
    applyColor(col, personaStar(p, vec2(0.612, -0.091), 118.516, 0.504, color1, color2, 1.0, pw, animTime));
    applyColor(col, personaStar(p, vec2(-0.793, 1.106), 7.135, 0.509, color1, accentColor, -1.0, pw, animTime));
    applyColor(col, personaStar(p, vec2(1.006, 0.940), 303.810, 0.443, color1, color2, -1.0, pw, animTime));
    applyColor(col, personaStar(p, vec2(-0.156, -0.402), 222.463, 0.556, color1, accentColor, 1.0, pw, animTime));

    fragColor = vec4(col, 1.0);
}
