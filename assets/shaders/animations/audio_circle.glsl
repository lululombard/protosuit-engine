#version 300 es
precision highp float;

// Audio Circle Visualization
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
uniform float gain;           // Master output gain
uniform float speed;          // Animation speed multiplier
uniform float ringRadius;     // Inner radius of FFT bars / waveform ring
uniform float barLength;      // FFT bar amplitude gain
uniform float glowIntensity;  // Glow effect intensity multiplier
uniform float rainbow;        // 1.0 = rainbow, 0.0 = solid baseColor
uniform vec3 baseColor;       // Solid color when rainbow is off

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

const float PI = 3.14159265359;

// Layout / behavior
const float SYMMETRY_TOGGLE = 1.0;        // 1.0 = mirror mapping, 0.0 = full 360 mapping
const float START_DEG = -90.0;            // spectral start angle
const float SCREEN_RADIUS = 0.98;         // circular screen mask

// Global motion
const float GLOBAL_WOBBLE_GAIN = 0.0035;
const float GLOBAL_WOBBLE_HZ = 0.55;

// Color system
const vec2 COLOR_ORIGIN_SCREEN = vec2(1.0, 0.0);
const float COLOR_CYCLES = 1.30;
const float COLOR_FLOW_SPEED = 0.52;
const float COLOR_SAT = 0.96;
const float COLOR_VAL = 1.00;

// Automatic gain for live mic dynamics
const float AGC_TARGET = 0.68;
const float AGC_FLOOR = 0.04;
const float AGC_MIN = 0.70;
const float AGC_MAX = 4.00;

// FFT bars layer
const float BAR_COUNT = 40.0;
const float BAR_WIDTH = 0.6;
const float BAR_REST_LEN = 0.001;          // minimum at true silence
const float BAR_FREQ_BIAS = 0.86;
const float BAR_AUDIO_EXP = 0.80;
const float BAR_ROT_SPEED_DEG = 6.0;
const float BAR_BASS_BOOST = 0.040;       // low-end extra length when bars are already active
const float BAR_NOISE_GATE = 0.070;        // reject mic hiss / room noise
const float BAR_NOISE_SOFT = 0.080;

// Global silence gate from raw (pre-AGC) energy
const float LIVE_GATE_LOW = 0.010;
const float LIVE_GATE_HIGH = 0.070;

// Waveform ring layer (time-domain)
const float WAVE_GAIN = 0.15;
const float WAVE_SHAPE = 0.74;
const float WAVE_LOWPASS = 0.78;          // 0 = raw, 1 = heavily smoothed
const float WAVE_LOWPASS_SPREAD = 18.0;   // max smoothing span in samples
const float WAVE_LINE_THICKNESS = 0.0001;
const float WAVE_GLOW_WIDTH = 0.040;
const float WAVE_SAMPLE_BIAS = 1.00;

// Oscilloscope-like trigger lock for waveform stabilization
const float WAVE_STABILIZE_TOGGLE = 1.0;
const float WAVE_STABILIZE_MIX = 1.0;
const float WAVE_TRIGGER_LEVEL = 0.50;
const float WAVE_TRIGGER_RANGE = 1.00;
const int WAVE_TRIGGER_STEPS = 24;

// Radial spokes / burst layer
const float SPOKE_COUNT = 30.0;
const float SPOKE_SPEED = 1.2;
const float SPOKE_SHARPNESS = 10.0;

// Center pulse + ripple
const float CORE_RADIUS = 0.11;
const float CORE_GLOW = 0.18;

// Subtle sparkles
const float SPARK_ANG_DENSITY = 72.0;
const float SPARK_RAD_DENSITY = 18.0;
const float SPARK_SIZE = 0.22;

// Final grading
const float MASTER_GAMMA = 0.92;

float fftTap(float u) {
    return texture(iChannel0, vec2(clamp(u, 0.0, 1.0), 0.25)).r;
}

float waveTap(float u) {
    return texture(iChannel0, vec2(clamp(u, 0.0, 1.0), 0.75)).r;
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

float waveSmoothBase(float u) {
    float du = 1.0 / 512.0;
    float s = 0.0;
    s += 0.06 * waveTap(u - 2.0 * du);
    s += 0.24 * waveTap(u - 1.0 * du);
    s += 0.40 * waveTap(u);
    s += 0.24 * waveTap(u + 1.0 * du);
    s += 0.06 * waveTap(u + 2.0 * du);
    return s;
}

float waveSmoothLowpass(float u) {
    float du = 1.0 / 512.0;
    float lp = clamp(WAVE_LOWPASS, 0.0, 1.0);
    float spread = mix(1.0, WAVE_LOWPASS_SPREAD, lp);

    float x0 = waveTap(u);
    float x1m = waveTap(u - spread * du);
    float x1p = waveTap(u + spread * du);
    float x2m = waveTap(u - 2.0 * spread * du);
    float x2p = waveTap(u + 2.0 * spread * du);
    float wide = 0.36 * x0 + 0.24 * (x1m + x1p) + 0.08 * (x2m + x2p);

    return mix(waveSmoothBase(u), wide, lp);
}

float spectralLevel(float u) {
    float du = 1.0 / 512.0;
    float e = 0.2 * fftSmooth(u - du) + 0.6 * fftSmooth(u) + 0.2 * fftSmooth(u + du);
    e = log(1.0 + 10.0 * e) / log(11.0);
    return pow(clamp(e, 0.0, 1.0), BAR_AUDIO_EXP);
}

float waveformSigned(float u) {
    float w = waveSmoothLowpass(u) * 2.0 - 1.0;
    float a = pow(abs(w), WAVE_SHAPE);
    return sign(w) * a;
}

float waveformTriggerOffset() {
    float range = clamp(WAVE_TRIGGER_RANGE, 0.05, 1.0);
    float level = clamp(WAVE_TRIGGER_LEVEL, 0.0, 1.0);

    float prevU = 0.0;
    float prev = waveTap(prevU);
    float found = 0.0;
    float triggerU = 0.0;

    for (int i = 1; i <= WAVE_TRIGGER_STEPS; i++) {
        float u = range * (float(i) / float(WAVE_TRIGGER_STEPS));
        float cur = waveTap(u);
        float slope = cur - prev;

        // Keep first rising crossing around trigger level.
        float cross = step(prev, level) * step(level, cur) * step(0.0, slope);
        float alpha = clamp((level - prev) / max(abs(slope), 1e-4), 0.0, 1.0);
        float uCross = mix(prevU, u, alpha);

        float take = (1.0 - found) * cross;
        triggerU = mix(triggerU, uCross, take);
        found = max(found, cross);

        prevU = u;
        prev = cur;
    }

    return triggerU;
}

float angularSample01(float angle01, float start01) {
    float rel = fract(angle01 - start01 + 1.0);
    float relMirror = (rel <= 0.5) ? (rel * 2.0) : ((1.0 - rel) * 2.0);
    return mix(rel, relMirror, clamp(SYMMETRY_TOGGLE, 0.0, 1.0));
}

vec4 audioBands() {
    float bass = 0.0;
    bass += fftSmooth(0.010);
    bass += fftSmooth(0.018);
    bass += fftSmooth(0.028);
    bass += fftSmooth(0.045);
    bass *= 0.25;

    float mid = 0.0;
    mid += fftSmooth(0.070);
    mid += fftSmooth(0.110);
    mid += fftSmooth(0.160);
    mid += fftSmooth(0.230);
    mid *= 0.25;

    float high = 0.0;
    high += fftSmooth(0.300);
    high += fftSmooth(0.420);
    high += fftSmooth(0.560);
    high += fftSmooth(0.740);
    high *= 0.25;

    // Live mic can vary a lot, so keep an automatic gain stage.
    float fullRaw = (bass + mid + high) / 3.0;
    float agc = clamp(AGC_TARGET / (AGC_FLOOR + fullRaw), AGC_MIN, AGC_MAX);

    bass = clamp(pow(bass * agc, 0.85), 0.0, 1.0);
    mid = clamp(pow(mid * agc, 0.90), 0.0, 1.0);
    high = clamp(pow(high * agc, 0.95), 0.0, 1.0);
    return vec4(bass, mid, high, fullRaw);
}

vec3 hsv2rgb(vec3 c) {
    vec3 rgb = clamp(abs(mod(c.x * 6.0 + vec3(0.0, 4.0, 2.0), 6.0) - 3.0) - 1.0, 0.0, 1.0);
    rgb = rgb * rgb * (3.0 - 2.0 * rgb);
    return c.z * mix(vec3(1.0), rgb, c.y);
}

float hash21(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 34.45);
    return fract(p.x * p.y);
}

void mainImage(out vec4 fragColor_out, in vec2 fragCoord) {
    float t = iTime * speed;
    float minRes = min(iResolution.x, iResolution.y);
    float aa = 2.0 / minRes;

    // Derive dependent radii from ringRadius
    float waveBaseRadius = ringRadius - 0.07;
    float spokeInnerRadius = ringRadius - 0.12;
    float spokeOuterRadius = SCREEN_RADIUS - 0.08;

    float globalWobblePhase = t * (2.0 * PI * GLOBAL_WOBBLE_HZ);
    vec2 uvBase = (fragCoord - 0.5 * iResolution.xy) / minRes;
    vec2 globalShake = GLOBAL_WOBBLE_GAIN * vec2(
        sin(globalWobblePhase),
        cos(globalWobblePhase * 1.17 + 1.1)
    );
    vec2 uv = uvBase + globalShake;

    vec2 st = (uv * minRes + 0.5 * iResolution.xy) / iResolution.xy;
    float r = length(uv);
    float angle = atan(uv.y, uv.x);
    float angle01 = fract(angle / (2.0 * PI) + 1.0);
    float start01 = fract(START_DEG / 360.0 + 1.0);

    vec4 bands = audioBands();
    float bass = bands.x;
    float mid = bands.y;
    float high = bands.z;
    float rawLevel = bands.w;
    float liveGate = smoothstep(LIVE_GATE_LOW, LIVE_GATE_HIGH, rawLevel);

    float sample01 = angularSample01(angle01, start01);

    // FFT bars (outer crown)
    float barAngle01 = fract((angle + radians(BAR_ROT_SPEED_DEG) * t) / (2.0 * PI) + 1.0);
    float barSample01 = angularSample01(barAngle01, start01);
    float barPhase = barSample01 * BAR_COUNT;
    float barIdx = floor(barPhase);
    float uBar = pow((barIdx + 0.5) / BAR_COUNT, BAR_FREQ_BIAS);
    float barRaw = spectralLevel(uBar);
    float barGate = smoothstep(BAR_NOISE_GATE, BAR_NOISE_GATE + BAR_NOISE_SOFT, barRaw);
    float barAmp = clamp(barRaw * barGate * (0.85 + 0.50 * mid), 0.0, 1.0);
    barAmp *= liveGate;

    float barInner = ringRadius - 0.03 * bass * liveGate;
    float barLen = mix(0.0, BAR_REST_LEN, liveGate) + barLength * barAmp + BAR_BASS_BOOST * bass * barAmp;
    float barOuter = barInner + barLen;
    float inBar = abs(fract(barPhase) - 0.5);
    float aaBar = fwidth(barPhase) + 0.002;
    float barMaskAng = 1.0 - smoothstep(0.5 * BAR_WIDTH, 0.5 * BAR_WIDTH + aaBar, inBar);
    float barMaskRad = smoothstep(barInner - aa, barInner + aa, r);
    barMaskRad *= 1.0 - smoothstep(barOuter - aa, barOuter + aa, r);
    // Continuous AA gate: keeps response to very small BAR_REST_LEN values.
    float barLenGate = clamp(barLen / (barLen + 0.75 * aa), 0.0, 1.0);
    float bars = barMaskAng * barMaskRad * barLenGate;

    // Stabilized waveform ring
    float triggerU = waveformTriggerOffset();
    float stabilize = clamp(WAVE_STABILIZE_TOGGLE, 0.0, 1.0) * clamp(WAVE_STABILIZE_MIX, 0.0, 1.0);
    float sampleLocked = fract(sample01 + triggerU);
    float sampleStable = mix(sample01, sampleLocked, stabilize);

    float uWave = pow(clamp(sampleStable, 0.0, 1.0), WAVE_SAMPLE_BIAS);
    float wave = waveformSigned(uWave);
    float waveRadius = waveBaseRadius + WAVE_GAIN * wave + 0.012 * sin(t * 5.0) * bass;
    float dr = abs(r - waveRadius);
    float waveLine = 1.0 - smoothstep(WAVE_LINE_THICKNESS, WAVE_LINE_THICKNESS + aa, dr);
    float waveGlowWidth = WAVE_GLOW_WIDTH * glowIntensity;
    float waveGlow = 1.0 - smoothstep(WAVE_LINE_THICKNESS, WAVE_LINE_THICKNESS + waveGlowWidth, dr);
    waveGlow *= 0.45 + 0.55 * mid;

    // Radial spokes / burst
    float spokeCount = mix(SPOKE_COUNT, SPOKE_COUNT * 1.8, high);
    float spokeCarrier = abs(sin(angle * spokeCount + t * (SPOKE_SPEED + 4.0 * mid)));
    float spokes = pow(1.0 - spokeCarrier, SPOKE_SHARPNESS);
    float spokeGate = smoothstep(spokeInnerRadius, spokeInnerRadius + 0.06, r);
    spokeGate *= 1.0 - smoothstep(spokeOuterRadius - 0.06, spokeOuterRadius, r);
    spokes *= spokeGate * (0.18 + 0.95 * high);

    // Center pulse + expanding ripple
    float coreR = CORE_RADIUS + 0.010 * sin(t * 6.0 + 10.0 * bass);
    float core = 1.0 - smoothstep(coreR - aa, coreR + aa, r);
    float coreGlowRadius = CORE_GLOW * glowIntensity;
    float coreGlow = 1.0 - smoothstep(coreR, coreR + coreGlowRadius, r);
    float coreLayer = core * (0.20 + 1.20 * pow(bass, 1.35));
    coreLayer += coreGlow * (0.10 + 0.55 * bass);

    float beat = smoothstep(0.35, 0.90, bass);
    float ripplePhase = fract(t * (0.35 + 1.8 * beat));
    float rippleRadius = mix(0.15, 0.95, ripplePhase);
    float ripple = 1.0 - smoothstep(0.0, 0.018, abs(r - rippleRadius));
    ripple *= beat * (1.0 - ripplePhase);

    // Sparkles in ring cells
    vec2 sparkGrid = vec2(angle01 * SPARK_ANG_DENSITY, r * SPARK_RAD_DENSITY);
    vec2 sparkCell = floor(sparkGrid);
    vec2 sparkLocal = fract(sparkGrid) - 0.5;
    float h = hash21(sparkCell);
    float twinkle = 0.5 + 0.5 * sin(t * (4.0 + 8.0 * h) + 6.28318 * h);
    float sparkShape = 1.0 - smoothstep(SPARK_SIZE, SPARK_SIZE + 0.12, length(sparkLocal));
    float sparkGate = smoothstep(0.28, 0.34, r) * (1.0 - smoothstep(0.93, 0.98, r));
    float sparks = step(0.965, h) * twinkle * sparkShape * sparkGate * high;

    // Rainbow source + tone variants
    float dist01 = distance(st, COLOR_ORIGIN_SCREEN) / 1.41421356;
    // Keep hue continuous in angle to avoid seam lines.
    float hue = fract(dist01 * COLOR_CYCLES - t * COLOR_FLOW_SPEED);

    vec3 mainColor = hsv2rgb(vec3(hue, COLOR_SAT, COLOR_VAL));
    vec3 accentColor = hsv2rgb(vec3(fract(hue + 0.13 + 0.10 * high), min(1.0, COLOR_SAT + 0.02), COLOR_VAL));
    float rainbowMix = clamp(rainbow, 0.0, 1.0);
    mainColor = mix(baseColor, mainColor, rainbowMix);
    accentColor = mix(baseColor, accentColor, rainbowMix);

    // Background haze inside circular screen
    float bgRad = pow(clamp(1.0 - r / SCREEN_RADIUS, 0.0, 1.0), 1.15);
    float haze = 0.5 + 0.5 * sin(t * 0.30 + angle * 3.0 + r * 14.0);
    float bg = 0.05 * bgRad * (0.55 + 0.45 * haze) * (0.35 + 0.65 * mid) * (0.30 + 0.70 * liveGate);

    vec3 color = vec3(0.0);
    color += mainColor * bg;
    color += mainColor * (bars * (0.90 + 0.90 * mid));
    color += accentColor * (waveLine * 1.35 + waveGlow * 0.60);
    color += mainColor * (spokes * 0.85);
    color += accentColor * (coreLayer * 0.95 + ripple * 0.75);
    color += vec3(1.0) * sparks * (0.40 + 1.70 * high);

    // Slight edge taming + circular mask
    float edge = smoothstep(SCREEN_RADIUS - 0.18, SCREEN_RADIUS, r);
    color *= mix(1.0, 0.55 + 0.35 * bass, edge);

    float mask = 1.0 - smoothstep(SCREEN_RADIUS - aa, SCREEN_RADIUS + aa, r);
    color *= mask;

    color = 1.0 - exp(-color * gain);
    color = pow(color, vec3(MASTER_GAMMA));

    fragColor_out = vec4(color, 1.0);
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
