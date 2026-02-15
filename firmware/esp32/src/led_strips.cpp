#include "led_strips.h"
#include "config.h"
#include <FastLED.h>

static CRGB ledsUpperArch[LED_UPPER_ARCH_COUNT];
static CRGB ledsRightEar[LED_RIGHT_EAR_COUNT];
static CRGB ledsRightFin[LED_RIGHT_FIN_COUNT];
static CRGB ledsLeftFin[LED_LEFT_FIN_COUNT];
static CRGB ledsLeftEar[LED_LEFT_EAR_COUNT];

// Snapshot buffer for per-pixel crossfade transitions
static CRGB snapshot[LED_TOTAL_COUNT];

// Strip info for iteration
struct StripInfo {
    CRGB* leds;
    int count;
};
static StripInfo strips[] = {
    {ledsUpperArch, LED_UPPER_ARCH_COUNT},
    {ledsRightEar,  LED_RIGHT_EAR_COUNT},
    {ledsRightFin,  LED_RIGHT_FIN_COUNT},
    {ledsLeftFin,   LED_LEFT_FIN_COUNT},
    {ledsLeftEar,   LED_LEFT_EAR_COUNT},
};
static const int NUM_STRIPS = 5;

// Target parameters (set by external calls)
static uint8_t targetColor = 0;
static uint8_t targetHueF = 0;
static uint8_t targetHueB = 0;
static uint8_t targetBright = 75;
static uint8_t targetFace = 0;
static bool targetBooped = false;

// Transition state
static const unsigned long TRANSITION_MS = 667; // 40 frames @ 60fps
static uint8_t transFromBright = 75;
static uint8_t transToBright = 75;
static unsigned long transStart = 0;
static bool transActive = false;

// Current output state
static uint8_t outputBright = 75;
static bool ready = false; // Stay off until first Teensy sync
static bool needsRedraw = true; // Force at least one draw after change

// Wave parameters for BASE color mode
static const float WAVE_WAVELENGTH = 60.0f;
static const float WAVE_PERIOD_MS = 3000.0f;

enum ColorIndex {
    COLOR_BASE = 0,
    COLOR_YELLOW, COLOR_ORANGE, COLOR_WHITE, COLOR_GREEN,
    COLOR_PURPLE, COLOR_RED, COLOR_BLUE,
    COLOR_RAINBOW, COLOR_RAINBOWNOISE, COLOR_FLOWNOISE, COLOR_HORIZONTALRAINBOW,
    COLOR_BLACK
};

static const CRGB solidColors[] = {
    CRGB::Black,          // 0: BASE (uses hueF/hueB wave)
    CRGB(255, 255, 0),    // 1: YELLOW
    CRGB(255, 165, 0),    // 2: ORANGE
    CRGB(255, 255, 255),  // 3: WHITE
    CRGB(0, 255, 0),      // 4: GREEN
    CRGB(255, 0, 255),    // 5: PURPLE
    CRGB(255, 0, 0),      // 6: RED
    CRGB(0, 0, 255),      // 7: BLUE
    CRGB::Black,          // 8-11: animated
    CRGB::Black, CRGB::Black, CRGB::Black,
    CRGB::Black           // 12: BLACK
};

static bool isAnimatedColor(uint8_t color) {
    return color >= COLOR_RAINBOW && color <= COLOR_HORIZONTALRAINBOW;
}

// Whether current mode needs per-frame rendering
static bool isContinuous() {
    if (targetBooped) return true;
    if (targetFace != 1 && targetFace != 5 && isAnimatedColor(targetColor)) return true;
    if (!targetBooped && targetFace != 1 && targetFace != 5
        && targetColor == COLOR_BASE && targetHueF != targetHueB) return true;
    return false;
}

// Cosine easing: 0→1 with smooth start and end
static float cosineEase(float t) {
    return (1.0f - cosf(t * PI)) * 0.5f;
}

static void fillAll(CRGB color) {
    for (int s = 0; s < NUM_STRIPS; s++) {
        fill_solid(strips[s].leds, strips[s].count, color);
    }
}

// Snapshot current LED arrays (what's on screen) for crossfade
static void takeSnapshot() {
    int offset = 0;
    for (int s = 0; s < NUM_STRIPS; s++) {
        memcpy(&snapshot[offset], strips[s].leds, strips[s].count * sizeof(CRGB));
        offset += strips[s].count;
    }
}

// Blend LED arrays with snapshot: leds[i] = blend(snapshot[i], leds[i], ratio)
static void blendFromSnapshot(uint8_t ratio) {
    int offset = 0;
    for (int s = 0; s < NUM_STRIPS; s++) {
        for (int i = 0; i < strips[s].count; i++) {
            strips[s].leds[i] = blend(snapshot[offset + i], strips[s].leds[i], ratio);
        }
        offset += strips[s].count;
    }
}

// Compute the target frame into LED arrays for the current mode
static void computeTargetFrame(unsigned long now) {
    // Priority 1: Boop → rainbow
    if (targetBooped) {
        uint8_t startHue = (now / 10) & 0xFF;
        for (int s = 0; s < NUM_STRIPS; s++) {
            fill_rainbow(strips[s].leds, strips[s].count, startHue, -3);
        }
        return;
    }

    // Priority 2: Face overrides
    if (targetFace == 1) { fillAll(CRGB(255, 0, 0)); return; } // ANGRY
    if (targetFace == 5) { fillAll(CRGB(0, 0, 255)); return; } // SAD

    // Priority 3: Animated rainbow colors
    if (isAnimatedColor(targetColor)) {
        uint8_t startHue = (now / 10) & 0xFF;
        for (int s = 0; s < NUM_STRIPS; s++) {
            fill_rainbow(strips[s].leds, strips[s].count, startHue, -3);
        }
        return;
    }

    // Priority 4: BASE color
    if (targetColor == COLOR_BASE) {
        if (targetHueF != targetHueB) {
            // Wave mode: sine blend between hueF and hueB
            float phase = (float)now / WAVE_PERIOD_MS * 2.0f * PI;
            CRGB colorF = CHSV(targetHueF, 255, 255);
            CRGB colorB = CHSV(targetHueB, 255, 255);
            for (int s = 0; s < NUM_STRIPS; s++) {
                for (int i = 0; i < strips[s].count; i++) {
                    float wave = (sinf(2.0f * PI * (float)i / WAVE_WAVELENGTH - phase) + 1.0f) * 0.5f;
                    strips[s].leds[i] = blend(colorF, colorB, (uint8_t)(wave * 255.0f));
                }
            }
        } else {
            fillAll(CHSV(targetHueF, 255, 255));
        }
        return;
    }

    // Priority 5: Solid named colors
    if (targetColor <= COLOR_BLACK) {
        fillAll(solidColors[targetColor]);
    } else {
        fillAll(CRGB::Black);
    }
}

// Start a crossfade transition
static void beginTransition(uint8_t newBright) {
    takeSnapshot();
    transFromBright = outputBright;
    transToBright = newBright;
    transStart = millis();
    transActive = true;
}

void ledStripsInit() {
    FastLED.addLeds<WS2812B, LED_UPPER_ARCH_PIN, GRB>(ledsUpperArch, LED_UPPER_ARCH_COUNT);
    FastLED.addLeds<WS2812B, LED_RIGHT_EAR_PIN, GRB>(ledsRightEar, LED_RIGHT_EAR_COUNT);
    FastLED.addLeds<WS2812B, LED_RIGHT_FIN_PIN, GRB>(ledsRightFin, LED_RIGHT_FIN_COUNT);
    FastLED.addLeds<WS2812B, LED_LEFT_FIN_PIN, GRB>(ledsLeftFin, LED_LEFT_FIN_COUNT);
    FastLED.addLeds<WS2812B, LED_LEFT_EAR_PIN, GRB>(ledsLeftEar, LED_LEFT_EAR_COUNT);

    FastLED.setBrightness(outputBright);
    fillAll(CRGB::Black);
    FastLED.show();
}

void ledStripsUpdate() {
    if (!ready) return;

    unsigned long now = millis();
    bool continuous = isContinuous();

    // Static mode with no transition and no pending redraw — skip
    if (!continuous && !transActive && !needsRedraw) return;

    // 1. Compute target frame into LED arrays
    computeTargetFrame(now);

    // 2. If transitioning, blend from snapshot
    if (transActive) {
        float elapsed = (float)(now - transStart);
        float progress = elapsed / (float)TRANSITION_MS;

        if (progress >= 1.0f) {
            // Transition complete — target frame is already in LED arrays
            outputBright = transToBright;
            transActive = false;
        } else {
            float ratio = cosineEase(progress);
            uint8_t blend8 = (uint8_t)(ratio * 255.0f);
            blendFromSnapshot(blend8);
            outputBright = transFromBright + (uint8_t)((float)(transToBright - transFromBright) * ratio);
        }
    } else {
        outputBright = targetBright;
    }

    FastLED.setBrightness(outputBright);
    FastLED.show();
    needsRedraw = false;
}

void ledStripsSetColor(uint8_t colorIndex, uint8_t hueF, uint8_t hueB, uint8_t bright) {
    if (bright > MAX_BRIGHTNESS) bright = MAX_BRIGHTNESS;
    bool first = !ready;
    ready = true;

    bool changed = (colorIndex != targetColor || hueF != targetHueF
                 || hueB != targetHueB || bright != targetBright);
    if (!changed && !first) return;

    targetColor = colorIndex;
    targetHueF = hueF;
    targetHueB = hueB;
    targetBright = bright;

    // First call from Teensy sync: snap to color immediately
    if (first) {
        computeTargetFrame(millis());
        outputBright = bright;
        FastLED.setBrightness(outputBright);
        FastLED.show();
        return;
    }

    beginTransition(bright);
    needsRedraw = true;
}

void ledStripsSetBooped(bool booped) {
    if (booped == targetBooped) return;
    targetBooped = booped;
    beginTransition(targetBright);
    needsRedraw = true;
}

void ledStripsSetFace(uint8_t face) {
    if (face == targetFace) return;
    targetFace = face;
    beginTransition(targetBright);
    needsRedraw = true;
}
