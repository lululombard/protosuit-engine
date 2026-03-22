// ============================================================
//  PROTOGEN EYE — Transition T02 : Cube Split
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
#define MAX_SPLIT    0.32
#define SEAM_WIDTH   0.014

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

// Convertit coordonnées centrées normalisées → UV [0,1] pour texture sampling
vec2 toTexUV(vec2 uv_n) {
    return uv_n * min(resolution.x, resolution.y) / resolution.xy + 0.5;
}

const vec2 DIR_A = vec2(-0.5,  0.866025);
const vec2 DIR_B = vec2(-0.5, -0.866025);
const vec2 DIR_C = vec2( 1.0,  0.0     );

bool inSector(vec2 q, vec2 dir) {
    if (dir.y > 0.5)  return dot(q, DIR_A) >= dot(q, DIR_B) && dot(q, DIR_A) >= dot(q, DIR_C);
    if (dir.y < -0.5) return dot(q, DIR_B) >= dot(q, DIR_A) && dot(q, DIR_B) >= dot(q, DIR_C);
    return dot(q, DIR_C) >= dot(q, DIR_A) && dot(q, DIR_C) >= dot(q, DIR_B);
}

bool sampleFace(vec2 p, vec2 dir, float split, float angle, bool useIn, out vec3 result) {
    vec2 q = p - dir * split;
    if (!inSector(q, dir)) { result = vec3(0.0); return false; }
    vec2 uvQ = rot2D(q, -angle);
    result = useIn ? texture(tex2, toTexUV(uvQ)).rgb : texture(tex1, toTexUV(uvQ)).rgb;
    return true;
}

void main() {
    vec2 res = resolution;
    vec2 uvN = (uv - 0.5) * vec2(res.x / min(res.x, res.y), res.y / min(res.x, res.y));

    float angle = mod(ROT_OFFSET + iTime * ROT_SPEED * TAU, PI3);
    vec2  p     = rot2D(uvN, angle);

    float splitOut = smoothstep(0.0, 0.5, alpha) * MAX_SPLIT;
    float splitIn  = (1.0 - smoothstep(0.5, 1.0, alpha)) * MAX_SPLIT;

    vec3 colOut = vec3(0.0);
    vec3 tmp;
    if      (sampleFace(p, DIR_A, splitOut, angle, false, tmp)) colOut = tmp;
    else if (sampleFace(p, DIR_B, splitOut, angle, false, tmp)) colOut = tmp;
    else if (sampleFace(p, DIR_C, splitOut, angle, false, tmp)) colOut = tmp;

    vec3 colIn = vec3(0.0);
    if      (sampleFace(p, DIR_A, splitIn, angle, true, tmp)) colIn = tmp;
    else if (sampleFace(p, DIR_B, splitIn, angle, true, tmp)) colIn = tmp;
    else if (sampleFace(p, DIR_C, splitIn, angle, true, tmp)) colIn = tmp;

    float t2  = smoothstep(0.38, 0.62, alpha);
    vec3  col = mix(colOut, colIn, t2);

    float dAB = abs(dot(p, vec2( 0.0,      1.0)));
    float dAC = abs(dot(p, vec2( 0.866025, 0.5)));
    float dBC = abs(dot(p, vec2( 0.866025,-0.5)));
    float seamAmp = alpha * (1.0 - alpha) * 4.0;

    col += HEX_COLOR                    * exp(-dAB / SEAM_WIDTH) * seamAmp * 2.5;
    col += COLOR_B                      * exp(-dAC / SEAM_WIDTH) * seamAmp * 2.5;
    col += mix(HEX_COLOR, COLOR_B, 0.5) * exp(-dBC / SEAM_WIDTH) * seamAmp * 2.5;

    float midFlash = exp(-abs(alpha - 0.5) * 18.0) * 0.25;
    col += vec3(midFlash);

    fragColor = vec4(col, 1.0);
}
