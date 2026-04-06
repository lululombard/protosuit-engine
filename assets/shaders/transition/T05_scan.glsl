// ============================================================
//  PROTOGEN EYE — Transition T05 : Neon Scan
//  Interface: tex1 = shader sortant, tex2 = shader entrant
//  alpha = progression 0.0 → 1.0, iTime = temps courant
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

#define ROT_OFFSET   0.5236
#define ROT_SPEED    0.0
#define HEX_COLOR    vec3(0.10, 0.72, 1.00)
#define COLOR_B      vec3(0.55, 0.00, 1.00)
#define COLOR_C      vec3(1.00, 1.00, 1.00)
#define TILE_R       0.045
#define GAP          0.003
#define FRONT_WIDTH  0.06
#define TRAIL_LEN    0.12

const float TAU = 6.28318530718;
const float PI3 = 1.04719755120;

float sdHexagon(vec2 p, float r) {
    const vec3 k = vec3(-0.866025404, 0.5, 0.577350269);
    p = abs(p);
    p -= 2.0 * min(dot(k.xy, p), 0.0) * k.xy;
    p -= vec2(clamp(p.x, -k.z * r, k.z * r), r);
    return length(p) * sign(p.y);
}

vec2 rot2D(vec2 p, float a) {
    float c = cos(a), s = sin(a);
    return vec2(c * p.x - s * p.y, s * p.x + c * p.y);
}

vec2 hexTile(vec2 p, float r) {
    vec2 per = vec2(r * 3.46410, r * 2.0);
    vec2 hp  = per * 0.5;
    vec2 a   = mod(p, per) - hp;
    vec2 b   = mod(p - hp, per) - hp;
    return dot(a, a) < dot(b, b) ? a : b;
}

void main() {
    vec2 res = resolution;
    vec2 uvN = (uv - 0.5) * vec2(res.x / min(res.x, res.y), res.y / min(res.x, res.y));

    float angle = mod(ROT_OFFSET + iTime * ROT_SPEED * TAU, PI3);
    vec2  p     = rot2D(uvN, angle);

    float aa = 1.5 / min(res.x, res.y);

    float ease   = smoothstep(0.0, 1.0, alpha);
    float frontY = ease * 1.4 - 0.7;
    float dFront = uvN.y - frontY;

    float cutWidth = aa * 2.0;
    float mainMask = smoothstep(cutWidth, -cutWidth, dFront);

    vec3 colOut = texture(tex1, uv).rgb;
    vec3 colIn  = texture(tex2, uv).rgb;
    vec3 col    = mix(colOut, colIn, mainMask);

    // Grille hex sur le front
    vec2  local   = hexTile(p, TILE_R);
    float hexD    = sdHexagon(local, TILE_R - GAP);
    float hexMask = smoothstep(aa, -aa, hexD);

    float trailBright = exp(min(0.0, dFront) / TRAIL_LEN) * step(0.0, -dFront) * hexMask * 0.4;
    float onEdge    = exp(-abs(dFront) / 0.008);
    float nearFront = exp(-abs(dFront) / (FRONT_WIDTH * 0.5));

    col += COLOR_C   * onEdge    * 1.8;
    col += HEX_COLOR * nearFront * hexMask * 2.0;
    col += COLOR_B   * trailBright * 1.2;

    float burn = smoothstep(0.0, -0.035, dFront) * smoothstep(-0.09, -0.035, dFront);
    col += HEX_COLOR * burn * 0.3;

    // Distorsion scanline au front (uvN.x pour l'espace centré, uv pour le sampling)
    float scanRipple = sin(uvN.x * 31.4 + iTime * 18.0) * 0.003 * onEdge;
    vec3  ripOut = texture(tex1, vec2(uv.x + scanRipple, uv.y)).rgb;
    vec3  ripIn  = texture(tex2, vec2(uv.x + scanRipple, uv.y)).rgb;
    col = mix(col, mix(ripOut, ripIn, mainMask) + HEX_COLOR * 0.6, onEdge * 0.35);

    fragColor = vec4(col, 1.0);
}
