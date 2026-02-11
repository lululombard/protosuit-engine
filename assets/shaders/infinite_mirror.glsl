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
uniform float depthCurve;     // fade curve (lower = smoother falloff)
uniform float glowStrength;   // halo brightness
uniform float brightness;     // overall exposure
uniform vec3  colorA;         // gradient color A
uniform vec3  colorB;         // gradient color B
uniform float bgGlow;         // background illumination from LEDs
uniform float bgFadeCurve;    // background fade curve (lower = smoother)

in vec2 v_fragCoord;
out vec4 fragColor;

#define PI 3.141592653589793
#define MAX_REPEATS 64

void mainImage(out vec4 fragColor_out, in vec2 fragCoord)
{
    // Aspect-correct coordinates (circle stays a circle on any resolution)
    vec2 p = (fragCoord - 0.5 * iResolution.xy) / iResolution.y;
    float r = length(p);

    // ---- Circular screen mask ----
    float screenR = 0.48;
    float aaR = max(fwidth(r), 1e-6);
    float insideScreen = 1.0 - smoothstep(screenR, screenR + aaR, r);

    // Early-out for pixels outside the circle
    if (insideScreen <= 0.0) {
        fragColor_out = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }

    // ---- Fixed parameters ----
    float ledFill  = 0.7;
    float blurStep = 0.30;
    float ringFill = 0.90;

    // sanitize
    float ledCountS = floor(ledCount + 0.5);
    ledCountS = max(1.0, ledCountS);

    // ---- LED geometry ----
    float borderR = screenR - 0.03;
    float sxBase = 0.030;
    float syBase = 0.014;
    float aspect = syBase / sxBase;

    // ---- "Light coming through" look ----
    float ledIntensity = 5.0;
    float glowGaussian = 140.0;
    float glowPower    = 0.75;
    float exposure     = brightness;
    float satBoost     = 4.0;
    float gamma        = 0.7;
    float glowCutoff   = 0.95;

    // ---- Polar coords (seam-free) ----
    float ang = (r > 1e-6) ? atan(p.y, p.x) : 0.0;
    float stepAng = 2.0 * PI / ledCountS;

    float ang01 = ang;
    if (ang01 < 0.0) ang01 += 2.0 * PI;

    float local = fract(ang01 / stepAng) - 0.5;

    float px = 1.0 / iResolution.y;

    // repeatCount=100 is always clamped to MAX_REPEATS
    int R = MAX_REPEATS;

    float denom = float(R - 1);
    float endR  = 0.001;

    float reflectEff0 = pow(endR / borderR, 1.0 / denom);

    float rimMargin = 0.02;
    float ratio = (screenR + rimMargin) / borderR;
    float outerExtraGeo = -log(max(ratio, 1.000001)) / log(clamp(reflectEff0, 1e-6, 0.999999));
    float period = max(denom + outerExtraGeo, 1.0);

    // Precompute angular gradient coordinate (0..1), rotating over time
    float angleT = fract(ang01 / (2.0 * PI) + iTime * rotateSpeed);
    // seamlessAngular=1.0 so angleCoord = angleCyclic
    float angleCoord = 0.5 - 0.5 * cos(2.0 * PI * angleT);

    // Precompute color blend (loop-invariant)
    float baseT = smoothstep(0.0, 1.0, angleCoord);
    vec3 baseColor = mix(colorA, colorB, baseT);

    // Background glow — LEDs illuminating the surface (behind everything)
    // Fades toward center like the LEDs do
    float bgFade = pow(smoothstep(0.0, screenR, r), bgFadeCurve);
    vec3 col = baseColor * bgGlow * bgFade;

    // ---- Accumulate repeated rings toward the center ----
    for (int i = 0; i < MAX_REPEATS; i++)
    {
        float fi = float(i);

        float depthIndex = fi - iTime * travelSpeed;
        float idxWrap = mod(depthIndex + outerExtraGeo, period) - outerExtraGeo;

        float ringR = borderR * pow(reflectEff0, idxWrap);
        float depth = max(idxWrap, 0.0);

        // sizePower=1.0 so s = scale
        float s = ringR / borderR;

        float slotArc = ringR * stepAng;

        float sxBaseL = sxBase * s;

        float sx = min(sxBaseL, 0.5 * slotArc * ledFill);
        sx = max(sx, 0.0012 * s);

        float sy = sx * aspect;

        float stepR = ringR - ringR * reflectEff0;
        float syMax = 0.5 * stepR * ringFill;
        if (sy > syMax) {
            sy = syMax;
            sx = sy / aspect;
        }

        // Skip sub-pixel LEDs near the center
        if (max(sx, sy) < px) continue;

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

        float atten = pow(depthFade, pow(depth, depthCurve));

        // radialDominance=0.35, radialPower=1.0
        float radial01 = 1.0 - clamp((ringR - endR) / (borderR - endR), 0.0, 1.0);
        float radT = smoothstep(0.0, 1.0, radial01);
        vec3 radialColor = mix(colorA, colorB, radT);
        vec3 ledColor = mix(baseColor, radialColor, 0.35);

        col += ledColor * atten * (ledIntensity * core + glowStrength * glow);
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

    col = pow(clamp(col, 0.0, 1.0), vec3(1.0 / gamma));

    col *= insideScreen * vignette;

    fragColor_out = vec4(col, 1.0);
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
