// ============================================================
//  PROTOGEN EYE — Transition T04 : Hex Boolean Switch
//  Interface: tex1 = shader sortant, tex2 = shader entrant
//  alpha = progression 0.0 → 1.0, iTime = temps courant
//  Quand l'onde passe le centre d'un pavé → switch instantané
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

#define TILE_R    0.055
#define GAP       0.003
#define WAVE_DIST 0.85

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

    float angle = mod(iTime * 0.02 * TAU, PI3);
    vec2  p     = rot2D(uvN, angle);

    vec2  local  = hexTile(p, TILE_R);
    vec2  center = p - local;
    float dist   = length(center);
    float h      = hash21(center * 31.7);

    // Max dist to screen corner (accounts for aspect ratio)
    vec2  screenCorner = vec2(res.x, res.y) * 0.5 / min(res.x, res.y);
    float maxDist = length(screenCorner) + TILE_R;

    // waveFront starts negative (no tile switched at alpha=0), reaches maxDist at alpha=1
    float waveFront = alpha * maxDist - TILE_R;
    float switched  = step(dist, waveFront);

    vec3 col = switched < 0.5 ? texture(tex1, uv).rgb : texture(tex2, uv).rgb;

    // Flash néon au moment du switch de chaque tile
    float switchP    = (dist + TILE_R) / maxDist;
    float localPhase = (alpha - switchP) / 0.07;
    float flashPeak  = exp(-localPhase * localPhase * 5.0);

    float d       = sdHexagon(local, TILE_R - 0.002);
    float rim     = exp(-abs(d) / (TILE_R * 0.30));
    vec3  flashCol = mix(vec3(0.0, 0.85, 1.0), vec3(1.0, 0.1, 0.9), h);
    col = mix(col, flashCol, flashPeak * rim * 0.90);

    fragColor = vec4(col, 1.0);
}
