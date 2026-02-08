// Original shader by Miggy
// Circular "screen" + evenly spaced oval LEDs on the border
// Infinite-mirror style repeats with "light coming through" effect

#version 300 es
precision highp float;

// Standard uniforms
uniform float iTime;
uniform vec2 iResolution;

// Custom uniforms
uniform float ledCount;       // number of LEDs around the circle
uniform float travelSpeed;    // camera push-in speed (rings/sec)
uniform float rotateSpeed;    // color rotation speed (rotations/sec)
uniform float depthFade;      // darkening per ring (0..1)
uniform float glowStrength;   // halo brightness
uniform float brightness;     // overall exposure
uniform vec3  colorA;         // gradient color A
uniform vec3  colorB;         // gradient color B

in vec2 v_fragCoord;
out vec4 fragColor;

#define PI 3.141592653589793
#define MAX_REPEATS 64

vec3 hsv2rgb(vec3 c) {
    vec3 p = abs(fract(c.xxx + vec3(0.0, 2.0/3.0, 1.0/3.0)) * 6.0 - 3.0);
    vec3 rgb = clamp(p - 1.0, 0.0, 1.0);
    return c.z * mix(vec3(1.0), rgb, c.y);
}

void mainImage(out vec4 fragColor_out, in vec2 fragCoord)
{
    // Aspect-correct coordinates (circle stays a circle on any resolution)
    vec2 p = (fragCoord - 0.5 * iResolution.xy) / iResolution.y;
    float r = length(p);

    // ---- Circular screen mask ----
    float screenR = 0.48;
    float aaR = max(fwidth(r), 1e-6);
    float insideScreen = 1.0 - smoothstep(screenR, screenR + aaR, r);

    // ---- Fixed parameters ----
    float ledFill  = 0.7;
    float radialDominance = 0.35;
    float radialPower   = 1.00;
    float seamlessAngular = 1.0;
    float repeatCount  = 100.0;
    float blurStep     = 0.30;
    float spacingMode  = 0.0;
    float endRadius    = 0.00;
    float fitToEnd     = 1.0;
    float reflectScale = 0.92;
    float ringSpacing  = 0.024;
    float sizePower    = 1.0;
    float ringFill     = 0.90;

    // sanitize
    float ledCountS = floor(ledCount + 0.5);
    ledCountS = max(1.0, ledCountS);

    // ---- LED geometry ----
    float borderR = screenR - 0.03;
    float sxBase = 0.030;
    float syBase = 0.014;
    float edgeSoft = 1.25;

    // ---- "Light coming through" look ----
    float ledIntensity   = 3.0;
    float glowGaussian   = 140.0;
    float glowPower      = 0.75;
    float exposure       = brightness;
    float satBoost       = 1.05;
    float gamma          = 2.2;
    float glowCutoff     = 0.95;
    float streakStrength = 0.0;
    float streakCutoff   = 0.35;
    float streakWidthX   = 0.090;
    float streakWidthY   = 0.020;

    // ---- Polar coords (seam-free) ----
    float ang = (r > 1e-6) ? atan(p.y, p.x) : 0.0;
    float stepAng = 2.0 * PI / ledCountS;

    float ang01 = ang;
    if (ang01 < 0.0) ang01 += 2.0 * PI;

    float ringPhase = 0.0;
    ang01 += ringPhase;

    float local = fract(ang01 / stepAng) - 0.5;

    float px = 1.0 / iResolution.y;

    int R = int(floor(repeatCount + 0.5));
    R = clamp(R, 1, MAX_REPEATS);

    float denom = max(float(R - 1), 1.0);
    float endR  = clamp(endRadius, 0.001, borderR - 0.001);

    float ringSpacingEff = (borderR - endR) / denom;
    float reflectFit = pow(endR / max(borderR, 1e-6), 1.0 / denom);

    float reflectEff0 = (fitToEnd > 0.5) ? reflectFit : reflectScale;
    float stepREff0   = (fitToEnd > 0.5) ? ringSpacingEff : ringSpacing;

    float rimMargin = 0.02;

    float outerExtraEven = (screenR - borderR + rimMargin) / max(stepREff0, 1e-6) + 2.0;

    float ratio = (screenR + rimMargin) / max(borderR, 1e-6);
    float base = clamp(reflectEff0, 1e-6, 0.999999);
    float outerExtraGeo = -log(max(ratio, 1.000001)) / log(base);

    float outerExtra = (spacingMode < 0.5) ? outerExtraGeo : outerExtraEven;
    float period = max((float(R) - 1.0) + outerExtra, 1.0);

    // Precompute angular gradient coordinate (0..1), rotating over time
    float angleT = fract(ang01 / (2.0 * PI) + iTime * rotateSpeed);

    float angleCyclic = 0.5 - 0.5 * cos(2.0 * PI * angleT);
    float angleCoord  = mix(angleT, angleCyclic, clamp(seamlessAngular, 0.0, 1.0));

    vec3 col = vec3(0.0);

    // ---- Accumulate repeated rings toward the center ----
    for (int i = 0; i < MAX_REPEATS; i++)
    {
        if (i >= R) break;

        float fi = float(i);

        float depthIndex = fi - iTime * travelSpeed;
        float idxWrap = mod(depthIndex + outerExtra, period) - outerExtra;

        float ringR_even = borderR - idxWrap * stepREff0;
        float ringR_geo  = borderR * pow(reflectEff0, idxWrap);
        float ringR = (spacingMode < 0.5) ? ringR_geo : ringR_even;

        float depth = max(idxWrap, 0.0);

        float scale = ringR / max(borderR, 1e-6);
        float s = pow(scale, sizePower);

        float slotArc = ringR * stepAng;

        float sxBaseL = sxBase * s;
        float syBaseL = syBase * s;

        float sx = min(sxBaseL, 0.5 * slotArc * ledFill);
        sx = max(sx, 0.0012 * s);

        float ledScale = sx / max(sxBaseL, 1e-6);

        float aspect = syBase / max(sxBase, 1e-6);
        float sy = sx * aspect;

        float stepR = (spacingMode < 0.5) ? (ringR - ringR * reflectEff0) : stepREff0;
        float syMax = 0.5 * stepR * ringFill;
        if (sy > syMax) {
            sy = syMax;
            sx = sy / max(aspect, 1e-6);
            ledScale = sx / max(sxBaseL, 1e-6);
        }

        float streakWidthXScaled = max(streakWidthX * ledScale, 0.002 * s);
        float streakWidthYScaled = max(streakWidthY * ledScale, 0.002 * s);

        float dt = local * slotArc;
        float dr = r - ringR;

        float d0 = length(vec2(dt / sx, dr / sy)) - 1.0;

        float aa = 1.5 * px / max(min(sx, sy), 1e-6);

        float core = smoothstep(aa, -aa, d0);
        float dist = max(d0, 0.0);

        float g = glowGaussian / (1.0 + depth * blurStep);

        float glow = exp(-dist * dist * g);
        glow = pow(glow, glowPower);
        glow *= smoothstep(glowCutoff, 0.0, dist);

        float streak = exp(-abs(dt) / streakWidthXScaled) * exp(-abs(dr) / streakWidthYScaled) * glow;
        streak *= smoothstep(streakCutoff, 0.0, dist);

        float atten = pow(depthFade, depth);

        float radial01 = 1.0 - clamp((ringR - endR) / max(borderR - endR, 1e-6), 0.0, 1.0);
        radial01 = pow(radial01, radialPower);

        float d = clamp(radialDominance, 0.0, 1.0);

        float baseT = smoothstep(0.0, 1.0, angleCoord);
        float radT  = smoothstep(0.0, 1.0, radial01);

        vec3 baseColor  = mix(colorA, colorB, baseT);
        vec3 radialColor = mix(colorA, colorB, radT);

        vec3 ledColor = mix(baseColor, radialColor, d);

        col += ledColor * atten * (ledIntensity * core + glowStrength * glow + streakStrength * streak);
    }

    // Gentle vignette toward the rim
    float vignette = smoothstep(0.0, screenR, r);
    vignette = 1.0 - 0.20 * vignette * vignette;

    // Luminance-preserving tonemap
    col *= exposure;

    float lum = dot(col, vec3(0.2126, 0.7152, 0.0722));
    float mappedLum = lum / (1.0 + lum);

    col *= mappedLum / max(lum, 1e-6);

    col = mix(vec3(mappedLum), col, satBoost);

    col = pow(clamp(col, 0.0, 1.0), vec3(1.0 / max(gamma, 1e-6)));

    col *= insideScreen * vignette;

    fragColor_out = vec4(col, 1.0);
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
