// ============================================================
//  PROTOGEN EYE — Transition T06 : Hex Mosaic
//  Interface: tex1 = shader sortant, tex2 = shader entrant
//  alpha = progression 0.0 → 1.0, iTime = temps courant
//
//  Chaque pavé :
//    1. Part de tex1 (shader sortant)
//    2. Scintille aléatoirement pendant la transition
//    3. Se stabilise sur tex2 (shader entrant)
// ============================================================

#version 300 es
precision highp float;

in vec2 uv;

uniform sampler2D tex1;
uniform sampler2D tex2;
uniform float alpha;
uniform vec2 resolution;
uniform float iTime;

out vec4 fragColor;

#define TILE_R      0.055
#define SPREAD      0.85
#define TILE_DUR    0.15
#define FLICKER_MIN 8.0
#define FLICKER_RNG 8.0

const float TAU = 6.28318530718;
const float PI3 = 1.04719755120;

float sdHexagon(vec2 p, float r) {
    const vec3 k = vec3(-0.866025404, 0.5, 0.577350269);
    p = abs(p);
    p -= 2.0 * min(dot(k.xy, p), 0.0) * k.xy;
    p -= vec2(clamp(p.x, -k.z * r, k.z * r), r);
    return length(p) * (p.y >= 0.0 ? 1.0 : -1.0);
}

vec2 rot2D(vec2 p, float a) {
    float c = cos(a), s = sin(a);
    return vec2(c*p.x - s*p.y, s*p.x + c*p.y);
}

vec2 hexTile(vec2 p, float r) {
    vec2 per = vec2(r * 3.46410, r * 2.0);
    vec2 hp  = per * 0.5;
    vec2 a   = mod(p,      per) - hp;
    vec2 b   = mod(p - hp, per) - hp;
    return dot(a,a) < dot(b,b) ? a : b;
}

float hash21(vec2 p) {
    p = fract(p * vec2(127.1, 311.7)); p += dot(p, p + 47.53);
    return fract(p.x * p.y);
}

void main() {
    vec2 res = resolution;
    vec2 uvN = (uv - 0.5) * vec2(res.x / min(res.x, res.y), res.y / min(res.x, res.y));

    // Grille hex avec rotation constante (évite les artefacts de bord animés)
    const float GRID_ANGLE = 0.5236;
    vec2  p      = rot2D(uvN, GRID_ANGLE);
    vec2  local  = hexTile(p, TILE_R);
    // Snap center to grid to absorb fp-precision errors from mod() wrap boundaries
    vec2  per    = vec2(TILE_R * 3.46410, TILE_R * 2.0);
    vec2  center = round((p - local) / (per * 0.5)) * (per * 0.5);
    float h      = hash21(center * 47.3 + vec2(3.17, 7.43));

    float threshold = h * SPREAD;

    float permanentlyIn = step(threshold, alpha);

    float distToThresh = abs(alpha - threshold);
    float flickerAmt   = max(0.0, 1.0 - distToThresh / TILE_DUR);

    float flickRate = FLICKER_MIN + h * FLICKER_RNG;
    float tFlick    = floor(iTime * flickRate);
    float flickRand = hash21(vec2(h * 73.1, tFlick));

    float flickerIn = step(1.0 - flickerAmt, flickRand) * (1.0 - permanentlyIn);
    float showIn    = max(permanentlyIn, flickerIn);

    vec3 col = showIn > 0.5 ? texture(tex2, uv).rgb : texture(tex1, uv).rgb;

    fragColor = vec4(col, 1.0);
}
