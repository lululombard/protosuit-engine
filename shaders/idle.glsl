//!HOOK MAINPRESUB
//!BIND HOOKED
//!WIDTH 720
//!HEIGHT 720

// Persona 5 Style Starfield Animation
// Adapted from Shadertoy "Persona 5 menu background" by soilmaster
// https://www.shadertoy.com/view/sd2BWy
// Based on iquilezles.org/articles/distfunctions2d

// Color definitions
#define BLUE    vec3(0.1, 0.1, 0.8)
#define GREEN   vec3(0.3, 1.0, 0.3)
#define RED     vec3(0.8, 0.1, 0.1)
#define ORANGE  vec3(0.9, 0.5, 0.3)
#define BLACK   vec3(0.0)
#define WHITE   vec3(1.0)
#define GRAY    vec3(0.8)

// Math constants
#define M_PI     3.141592
#define RAD2DEG  (M_PI / 360.0 * 2.0)
#define DEG2RAD  (360.0 / M_PI / 2.0)

// 5-pointed star SDF (Signed Distance Function)
float sdfStar5(in vec2 p)
{
    // Repeat domain 5x for star symmetry
    const vec2 k1 = vec2(0.809016994375, -0.587785252292); // cos(π/5), sin(π/5)
    const vec2 k2 = vec2(-k1.x, k1.y);

    p.x = abs(p.x);
    p -= 2.0 * max(dot(k1, p), 0.0) * k1;
    p -= 2.0 * max(dot(k2, p), 0.0) * k2;

    // Draw triangle
    const vec2 k3 = vec2(0.951056516295, 0.309016994375); // cos(π/10), sin(π/10)
    return dot(vec2(abs(p.x) - 0.3, p.y), k3);
}

// Smooth square wave function for animation
float smoothSquareWave(float a, float blur)
{
    // Normalize to 0-1 period
    a = a - floor(a);

    // Ramp up at 0
    if (a <= 0.25) return smoothstep(-blur, blur, a);

    // Ramp up at 1
    if (a >= 0.75) return smoothstep(1.0 - blur, 1.0 + blur, a);

    // Ramp down at 0.5
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
    bool rippleDir,
    float globalPixelWidth,
    float iTime)
{
    // Transform coordinates: rotate, translate, and scale
    fragCoord = rotate2d(DEG2RAD * angle) * (fragCoord - position);
    fragCoord = scale2d(size) * fragCoord;
    float starPixelWidth = globalPixelWidth * size * 7.0;

    // Calculate distance to star shape
    float dist = sdfStar5(fragCoord);

    // Animate ripples with time
    vec4 col;
    float time = rippleDir ? iTime : -iTime;
    col = vec4(mix(col1, col2, smoothSquareWave(dist * 9.0 + 0.4 * time, starPixelWidth)), 1.0);

    // Create shape mask (alpha channel)
    col.a = 1.0 - smoothstep(0.0, globalPixelWidth * 2.0, dist);

    return col;
}

// Blend color with existing color using alpha
void applyColor(inout vec3 existingColor, vec4 inputColor)
{
    existingColor = mix(existingColor.xyz, inputColor.xyz, inputColor.a);
}

vec4 hook()
{
    vec2 iResolution = vec2(720.0, 720.0);
    vec2 fragCoord = HOOKED_pos * iResolution;

    // Use mpv's built-in frame counter for smooth animation
    float iTime = float(frame) * 0.08;

    // Normalize coordinates to [-1, 1] with aspect ratio correction
    vec2 p = (2.0 * fragCoord - iResolution.xy) / iResolution.y;
    float pw = 2.0 / iResolution.y;
    vec3 col = GREEN;

    // Render active stars
    applyColor(col, personaStar(p, vec2(-0.628, 0.903), 232.285, 0.401, WHITE, GRAY, true, pw, iTime));
    applyColor(col, personaStar(p, vec2(0.363, -0.717), 202.978, 0.550, WHITE, GRAY, true, pw, iTime));
    applyColor(col, personaStar(p, vec2(0.612, -0.091), 118.516, 0.504, WHITE, GRAY, true, pw, iTime));
    applyColor(col, personaStar(p, vec2(-0.793, 1.106), 7.135, 0.509, WHITE, BLACK, true, pw, iTime));
    applyColor(col, personaStar(p, vec2(1.006, 0.940), 303.810, 0.443, WHITE, GRAY, true, pw, iTime));
    applyColor(col, personaStar(p, vec2(-0.156, -0.402), 222.463, 0.556, WHITE, BLACK, true, pw, iTime));

    return vec4(col, 1.0);
}
