#version 300 es
precision highp float;

// Audio Circle Bars Visualization
// Created by Miggy

// Standard uniforms
uniform float iTime;
uniform int frame;
uniform vec2 iResolution;

// Audio data texture (512x2, R32F)
// Row 0 (y=0.25): FFT frequency magnitudes (0.0-1.0)
// Row 1 (y=0.75): Waveform samples (0.0-1.0, centered at 0.5)
uniform sampler2D iChannel0;

// MQTT-controllable uniforms
uniform float speed;          // Animation speed multiplier
uniform float ringRadius;     // Inner radius where bars start
uniform float barLength;      // FFT bar amplitude gain
uniform float barCount;       // Number of unique bars around the ring
uniform float rainbow;        // 1.0 = rainbow, 0.0 = solid baseColor
uniform vec3 baseColor;       // Solid color when rainbow is off

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

const float PI = 3.14159265359;

const float BAR_START_DEG = -90.0;
const float SYMMETRY_TOGGLE = 1.0;
const float BAR_ROT_SPEED_DEG = 5.0;
const float BASS_WOBBLE_GAIN = 0.060;
const float BASS_BASE_MIN_HZ = 35.0;
const float BASS_BASE_MAX_HZ = 180.0;
const float BASS_FUND_CUTOFF_HZ = 95.0;
const float BASS_FUND_CUTOFF_SOFT_U = 0.006;
const float BASS_WOBBLE_THRESHOLD = 0.10;
const float BASS_WOBBLE_SOFT = 0.22;
const float BASS_WOBBLE_RESPONSE = 1.00;
const float GLOBAL_WOBBLE_GAIN = 0.0035;
const float GLOBAL_WOBBLE_HZ = 0.55;
const float BAR_WOBBLE_HZ_MIN = 0.35;
const float BAR_WOBBLE_HZ_MAX = 2.4;
const float FREQ_TO_AMP_INFLUENCE = 1.00;
const float FUND_AMP_GAIN = 2.8;
const float FUND_AMP_THRESHOLD = 0.06;
const float FUND_AMP_SOFT = 0.18;
const float BAR_CURVE_SHIFT_GAIN = 0.48;
const float BAR_CURVE_MAX_SHIFT = 0.08;
const float BAR_CURVE_EXP_MIN = 1.15;
const float BAR_CURVE_EXP_MAX = 2.40;

const float FREQ_BIAS = 0.85;
const float BAR_WIDTH = 0.72;
const float MIN_BAR_LEN = 0.015;
const float AUDIO_EXP = 0.90;
const float AGC_TARGET = 0.68;
const float AGC_FLOOR = 0.04;
const float AGC_MIN = 0.70;
const float AGC_MAX = 4.00;
const float LIVE_GATE_LOW = 0.010;
const float LIVE_GATE_HIGH = 0.070;
const float BAR_NOISE_GATE = 0.050;
const float BAR_NOISE_SOFT = 0.080;

const float CENTER_RADIUS = 0.20;
const float CENTER_FALLBACK = 0.10;

const vec2 COLOR_ORIGIN_SCREEN = vec2(1.0, 0.0);
const float COLOR_CYCLES = 1.25;
const float COLOR_FLOW_SPEED = 0.45;
const float COLOR_SAT = 0.95;
const float COLOR_VAL = 1.00;

float fftTap(float u) {
    return texture(iChannel0, vec2(clamp(u, 0.0, 1.0), 0.25)).r;
}

float fftSmooth(float u) {
    float du = 1.0 / 512.0;
    float s = 0.0;
    s += 0.06 * fftTap(u - 2.0 * du);
    s += 0.24 * fftTap(u - 1.0 * du);
    s += 0.40 * fftTap(u);
    s += 0.24 * fftTap(u + 1.0 * du);
    s += 0.06 * fftTap(u + 2.0 * du);
    return s;
}

float barLevel(float u) {
    float du = 1.0 / 512.0;
    float e = fftSmooth(u);
    float energy = log(1.0 + 8.0 * e) / log(9.0);
    float edge = abs(fftSmooth(u + du) - fftSmooth(u - du));
    float detail = clamp(edge * 3.0, 0.0, 1.0);
    return mix(energy, detail, 0.35);
}

float rawEnergyLevel() {
    float e = 0.0;
    e += fftSmooth(0.010);
    e += fftSmooth(0.018);
    e += fftSmooth(0.028);
    e += fftSmooth(0.045);
    e += fftSmooth(0.070);
    e += fftSmooth(0.110);
    e += fftSmooth(0.160);
    e += fftSmooth(0.230);
    e += fftSmooth(0.300);
    e += fftSmooth(0.420);
    e += fftSmooth(0.560);
    e += fftSmooth(0.740);
    return e / 12.0;
}

float bassLevel() {
    float b = 0.0;
    b += fftSmooth(0.010);
    b += fftSmooth(0.020);
    b += fftSmooth(0.035);
    b += fftSmooth(0.055);
    b += fftSmooth(0.080);
    b *= 0.2;

    b = pow(clamp(b * 2.2, 0.0, 1.0), 0.85);
    return b;
}

vec2 bassFundamentalInfo() {
    float u0 = 0.010, u1 = 0.020, u2 = 0.032, u3 = 0.045, u4 = 0.060, u5 = 0.078, u6 = 0.095;
    float m0 = fftSmooth(u0);
    float m1 = fftSmooth(u1);
    float m2 = fftSmooth(u2);
    float m3 = fftSmooth(u3);
    float m4 = fftSmooth(u4);
    float m5 = fftSmooth(u5);
    float m6 = fftSmooth(u6);

    float cutT = clamp((BASS_FUND_CUTOFF_HZ - BASS_BASE_MIN_HZ) / (BASS_BASE_MAX_HZ - BASS_BASE_MIN_HZ), 0.0, 1.0);
    float maxU = mix(u0, u6, cutT);
    float g0 = 1.0 - smoothstep(maxU - BASS_FUND_CUTOFF_SOFT_U, maxU + BASS_FUND_CUTOFF_SOFT_U, u0);
    float g1 = 1.0 - smoothstep(maxU - BASS_FUND_CUTOFF_SOFT_U, maxU + BASS_FUND_CUTOFF_SOFT_U, u1);
    float g2 = 1.0 - smoothstep(maxU - BASS_FUND_CUTOFF_SOFT_U, maxU + BASS_FUND_CUTOFF_SOFT_U, u2);
    float g3 = 1.0 - smoothstep(maxU - BASS_FUND_CUTOFF_SOFT_U, maxU + BASS_FUND_CUTOFF_SOFT_U, u3);
    float g4 = 1.0 - smoothstep(maxU - BASS_FUND_CUTOFF_SOFT_U, maxU + BASS_FUND_CUTOFF_SOFT_U, u4);
    float g5 = 1.0 - smoothstep(maxU - BASS_FUND_CUTOFF_SOFT_U, maxU + BASS_FUND_CUTOFF_SOFT_U, u5);
    float g6 = 1.0 - smoothstep(maxU - BASS_FUND_CUTOFF_SOFT_U, maxU + BASS_FUND_CUTOFF_SOFT_U, u6);
    m0 *= g0; m1 *= g1; m2 *= g2; m3 *= g3; m4 *= g4; m5 *= g5; m6 *= g6;

    float mSum = m0 + m1 + m2 + m3 + m4 + m5 + m6;
    float bassCentroid = (u0 * m0 + u1 * m1 + u2 * m2 + u3 * m3 + u4 * m4 + u5 * m5 + u6 * m6) / max(mSum, 1e-5);

    float peakU = u0;
    float peakM = m0;
    if (m1 > peakM) { peakM = m1; peakU = u1; }
    if (m2 > peakM) { peakM = m2; peakU = u2; }
    if (m3 > peakM) { peakM = m3; peakU = u3; }
    if (m4 > peakM) { peakM = m4; peakU = u4; }
    if (m5 > peakM) { peakM = m5; peakU = u5; }
    if (m6 > peakM) { peakM = m6; peakU = u6; }

    float baseU = mix(bassCentroid, peakU, 0.65);
    float t = clamp((baseU - u0) / (u6 - u0), 0.0, 1.0);
    float baseHz = mix(BASS_BASE_MIN_HZ, BASS_BASE_MAX_HZ, pow(t, 1.15));
    baseHz = clamp(baseHz, BASS_BASE_MIN_HZ, BASS_FUND_CUTOFF_HZ);

    float meanM = mSum / 7.0;
    float fundRaw = max(peakM - 0.30 * meanM, 0.0);
    float fundAmp = smoothstep(FUND_AMP_THRESHOLD, FUND_AMP_THRESHOLD + FUND_AMP_SOFT, fundRaw * FUND_AMP_GAIN);

    return vec2(baseHz, clamp(fundAmp, 0.0, 1.0));
}

vec3 hsv2rgb(vec3 c) {
    vec3 rgb = clamp(abs(mod(c.x * 6.0 + vec3(0.0, 4.0, 2.0), 6.0) - 3.0) - 1.0, 0.0, 1.0);
    rgb = rgb * rgb * (3.0 - 2.0 * rgb);
    return c.z * mix(vec3(1.0), rgb, c.y);
}

void mainImage(out vec4 fragColor_out, in vec2 fragCoord) {
    float t = iTime * speed;

    float globalWobblePhase = t * (2.0 * PI * GLOBAL_WOBBLE_HZ);

    float minRes = min(iResolution.x, iResolution.y);
    vec2 uvBase = (fragCoord - 0.5 * iResolution.xy) / minRes;

    vec2 globalShake = GLOBAL_WOBBLE_GAIN * vec2(
        sin(globalWobblePhase),
        cos(globalWobblePhase * 1.17 + 1.1)
    );

    vec2 uv = uvBase + globalShake;
    vec2 st = (uv * minRes + 0.5 * iResolution.xy) / iResolution.xy;
    float r = length(uv);
    float rawLevel = rawEnergyLevel();
    float agc = clamp(AGC_TARGET / (AGC_FLOOR + rawLevel), AGC_MIN, AGC_MAX);
    float liveGate = smoothstep(LIVE_GATE_LOW, LIVE_GATE_HIGH, rawLevel);

    float barRot = radians(BAR_ROT_SPEED_DEG) * t;
    float angle = atan(uv.y, uv.x) + barRot;
    float angle01 = fract(angle / (2.0 * PI) + 1.0);

    float start01 = fract(BAR_START_DEG / 360.0 + 1.0);
    float rel = fract(angle01 - start01 + 1.0);
    float relMirror = (rel <= 0.5) ? (rel * 2.0) : ((1.0 - rel) * 2.0);
    float pos01 = mix(rel, relMirror, clamp(SYMMETRY_TOGGLE, 0.0, 1.0));

    float barPhaseData = pos01 * barCount;
    float barIdx = floor(barPhaseData);

    float u = (barIdx + 0.5) / barCount;
    u = pow(clamp(u, 0.0, 1.0), FREQ_BIAS);
    float d = 1.0 / barCount;
    float amp = 0.25 * barLevel(u - d) + 0.5 * barLevel(u) + 0.25 * barLevel(u + d);
    amp = pow(max(amp * agc, 0.0), AUDIO_EXP);
    float barGate = smoothstep(BAR_NOISE_GATE, BAR_NOISE_GATE + BAR_NOISE_SOFT, amp);
    amp *= barGate * liveGate;

    float barLen = mix(0.0, MIN_BAR_LEN, liveGate) + barLength * amp;
    float outerRadius = ringRadius + max(0.0, barLen);

    float barPhaseMask = barPhaseData;
    float inBar = abs(fract(barPhaseMask) - 0.5);
    float aaBar = fwidth(barPhaseMask) + 0.002;
    float barMaskAng = 1.0 - smoothstep(0.5 * BAR_WIDTH, 0.5 * BAR_WIDTH + aaBar, inBar);

    float aaRad = 2.0 / min(iResolution.x, iResolution.y);
    float barMaskRad = smoothstep(ringRadius - aaRad, ringRadius + aaRad, r);
    barMaskRad *= 1.0 - smoothstep(outerRadius - aaRad, outerRadius + aaRad, r);
    float barLenGate = clamp(barLen / (barLen + 0.75 * aaRad), 0.0, 1.0);

    float bars = barMaskAng * barMaskRad * barLenGate;

    float dist01 = distance(st, COLOR_ORIGIN_SCREEN) / 1.41421356;
    float hue = fract(dist01 * COLOR_CYCLES - t * COLOR_FLOW_SPEED);
    vec3 rainbowColor = hsv2rgb(vec3(hue, COLOR_SAT, COLOR_VAL));
    vec3 barsColor = mix(baseColor, rainbowColor, clamp(rainbow, 0.0, 1.0));

    vec3 color = bars * barsColor;

    float centerMask = 1.0 - smoothstep(CENTER_RADIUS - aaRad, CENTER_RADIUS + aaRad, r);
    color = mix(color, vec3(CENTER_FALLBACK), centerMask);

    fragColor_out = vec4(color, 1.0);
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
