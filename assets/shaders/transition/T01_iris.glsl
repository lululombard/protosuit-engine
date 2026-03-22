// ============================================================
//  PROTOGEN EYE — Transition T01 : Hexagonal Iris
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

#define ROT_OFFSET  0.5236
#define ROT_SPEED   0.0
#define HEX_COLOR   vec3(0.10, 0.72, 1.00)
#define COLOR_B     vec3(0.55, 0.00, 1.00)

const float TAU = 6.28318530718;
const float PI3 = 1.04719755120;

float sdHexagon(vec2 p, float r) {
    const vec3 k = vec3(-0.866025404, 0.5, 0.577350269);
    p = abs(p);
    p -= 2.0 * min(dot(k.xy, p), 0.0) * k.xy;
    p -= vec2(clamp(p.x, -k.z * r, k.z * r), r);
    return length(p) * sign(p.y);
}

float hexNorm(vec2 p) {
    float a = abs(dot(p, vec2(0.0,      1.0   )));
    float b = abs(dot(p, vec2(0.866025, 0.5   )));
    float c = abs(dot(p, vec2(0.866025, -0.5  )));
    return max(a, max(b, c));
}

vec2 rot2D(vec2 p, float a) {
    float c = cos(a), s = sin(a);
    return vec2(c * p.x - s * p.y, s * p.x + c * p.y);
}

void main() {
    vec2 res = resolution;
    vec2 uvN = (uv - 0.5) * vec2(res.x / min(res.x, res.y), res.y / min(res.x, res.y));

    float angle = mod(ROT_OFFSET + iTime * ROT_SPEED * TAU, PI3);
    vec2  p     = rot2D(uvN, angle);

    float aa = 1.5 / min(res.x, res.y);

    float ease   = 1.0 - pow(1.0 - alpha, 2.5);
    float irisR  = ease * 0.85;
    float d      = hexNorm(p) - irisR;

    float aaIris = aa * 4.0;
    float mask   = smoothstep(aaIris, -aaIris, d);

    vec3 colOut = texture(tex1, uv).rgb;
    vec3 colIn  = texture(tex2, uv).rgb;
    vec3 col    = mix(colOut, colIn, mask);

    float glow1 = exp(-abs(d) / 0.016) * 3.0;
    float glow2 = exp(-abs(d) / 0.06 ) * 0.75;
    float tint  = 0.5 + 0.5 * sin(iTime * 4.1 + alpha * 3.0);
    vec3  edge  = mix(HEX_COLOR, COLOR_B, tint);
    float edgeAmt = smoothstep(0.0, 0.06, alpha) * smoothstep(1.0, 0.94, alpha);
    col += edge    * glow1 * edgeAmt;
    col += COLOR_B * glow2 * edgeAmt;

    float flash = exp(-alpha * 12.0) * 0.6 * edgeAmt;
    col += vec3(flash);

    fragColor = vec4(col, 1.0);
}
