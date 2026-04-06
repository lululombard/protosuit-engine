// ============================================================
//  PROTOGEN EYE — Transition T03 : Digital Glitch
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
uniform float blurEnabled;
uniform float blurStrengthMax;

out vec4 fragColor;

const float TAU = 6.28318530718;
const float PI  = 3.14159265359;

float hash21(vec2 p) { p=fract(p*vec2(127.1,311.7)); p+=dot(p,p+47.53); return fract(p.x*p.y); }
float hash11(float x) { return hash21(vec2(x, x*1.7+3.1)); }

void main() {
    vec2 res = resolution;
    // Convertir uv (0..1) en coordonnées centrées normalisées
    vec2 uvN = (uv - 0.5) * vec2(res.x / min(res.x, res.y), res.y / min(res.x, res.y));
    float y01 = uv.y;

    float glitchAmt = sin(alpha * PI)
                    * smoothstep(0.0, 0.04, alpha)
                    * smoothstep(1.0, 0.96, alpha);
    float phase = smoothstep(0.35, 0.65, alpha);

    // ══ 1. DÉFILEMENT VERTICAL GLOBAL ══════════════════════════════════════
    float tV = floor(iTime * 2.5);
    float vJumpAmt  = (hash21(vec2(tV, 0.0)) - 0.5) * 0.55 * glitchAmt;
    float vJumpAct  = step(0.60, hash21(vec2(tV, 1.0)));
    float vScroll   = vJumpAmt * vJumpAct;
    vScroll += sin(iTime * 0.7) * 0.015 * glitchAmt;

    // ══ 2. DÉPLACEMENT HORIZONTAL PAR BREAK-POINTS ═════════════════════════
    float tB = floor(iTime * 6.5);
    float by0 = hash21(vec2(tB, 10.0));
    float bx0 = (hash21(vec2(tB, 11.0)) - 0.5) * 0.7 * step(0.45, glitchAmt);
    float by1 = hash21(vec2(tB, 20.0));
    float bx1 = (hash21(vec2(tB, 21.0)) - 0.5) * 0.45;
    float by2 = hash21(vec2(tB, 30.0));
    float bx2 = (hash21(vec2(tB, 31.0)) - 0.5) * 1.1 * step(0.72, glitchAmt);

    float wobX0  = floor(uv.x * 55.0);
    float wobX1  = floor(uv.x * 38.0);
    float wobX2  = floor(uv.x * 72.0);
    float tWob0  = floor(iTime * 19.0);
    float tWob1  = floor(iTime * 12.0);
    float tWob2  = floor(iTime * 31.0);
    float yWob0  = (hash21(vec2(wobX0, tWob0)) - 0.5) * 0.016;
    float yWob1  = (hash21(vec2(wobX1, tWob1 + 5.0)) - 0.5) * 0.020;
    float yWob2  = (hash21(vec2(wobX2, tWob2 + 9.0)) - 0.5) * 0.024;

    float hDisp = 0.0;
    hDisp += bx0 * step(by0, y01 + yWob0);
    hDisp += bx1 * step(by1, y01 + yWob1);
    hDisp += bx2 * step(by2, y01 + yWob2) * step(0.72, glitchAmt);
    hDisp *= glitchAmt;

    float ca = abs(hDisp) * 0.2 + glitchAmt * 0.008
             + sin(y01 * 47.3 + iTime * 11.0) * 0.006 * glitchAmt;

    // UV distordus pour sampling (en espace 0..1)
    vec2 uvD = vec2(uv.x + hDisp, uv.y + vScroll);

    // ── Sample tex1 (sortant) et tex2 (entrant) avec aberration chromatique ──
    vec3 colOut = vec3(
        texture(tex1, vec2(uvD.x + ca,       uvD.y)).r,
        texture(tex1, uvD).g,
        texture(tex1, vec2(uvD.x - ca * 0.6, uvD.y)).b
    );
    vec3 colIn = vec3(
        texture(tex2, vec2(uvD.x + ca * 0.5, uvD.y)).r,
        texture(tex2, uvD).g,
        texture(tex2, vec2(uvD.x - ca * 0.3, uvD.y)).b
    );

    vec3 col = mix(colOut, colIn, phase);

    // ══ 3. RECTANGLES HORS-PLACE ═══════════════════════════════════════════
    for (int i = 0; i < 5; i++) {
        float fi  = float(i);
        float tR  = floor(iTime * (3.5 + fi * 1.1));
        float rx  = hash21(vec2(fi*7.1+0.0, tR)) - 0.5;
        float ry  = hash21(vec2(fi*7.1+1.0, tR)) - 0.5;
        float rw  = hash21(vec2(fi*7.1+2.0, tR)) * 0.38 + 0.04;
        float rh  = hash21(vec2(fi*7.1+3.0, tR)) * 0.22 + 0.02;
        float ra  = step(0.42, hash21(vec2(fi*7.1+4.0, tR)))
                  * step(0.28, glitchAmt);
        float sox = hash21(vec2(fi*7.1+5.0, tR)) - 0.5;
        float soy = hash21(vec2(fi*7.1+6.0, tR)) - 0.5;
        float src = hash21(vec2(fi*7.1+7.0, tR));

        vec2 srcUV = vec2(uv.x + sox, uv.y + soy);
        vec3 rectCol = mix(texture(tex1, srcUV).rgb, texture(tex2, srcUV).rgb, step(0.5, src));

        float inRect = step(abs(uvN.x - rx), rw*0.5) * step(abs(uvN.y - ry), rh*0.5);
        col = mix(col, rectCol, inRect * ra);
    }

    // ══ 4. LIGNES VERTICALES CORROMPUES ════════════════════════════════════
    float lineX   = floor(uv.x * 420.0);
    float lineRate = 2.0 + hash11(lineX) * 11.0;
    float tLn     = floor(iTime * lineRate);
    float lineAct = step(0.982, hash21(vec2(lineX, tLn))) * glitchAmt;
    float lineVal = step(0.85, hash21(vec2(lineX + 3.0, tLn))) * 0.9;
    col = mix(col, vec3(lineVal), lineAct);

    // ══ 5. ÉCRAN NOIR ══════════════════════════════════════════════════════
    float tBl  = floor(iTime * 18.0);
    float isBlack = step(0.97, hash21(vec2(tBl, 55.0))) * glitchAmt;
    col = mix(col, vec3(0.0), isBlack);

    // ══ 6. NEIGE BLANCHE ═══════════════════════════════════════════════════
    float tWn  = floor(iTime * 22.0);
    float isNoise = step(0.985, hash21(vec2(tWn, 66.0))) * step(0.5, glitchAmt);
    float snow = hash21(uv * vec2(431.0, 317.0) + tWn);
    col = mix(col, vec3(snow), isNoise);

    // ══ 7. SCINTILLEMENT GLOBAL ════════════════════════════════════════════
    float tFl = floor(iTime * 24.0);
    float flicker = hash21(vec2(tFl, 33.0));
    float flickAmt = smoothstep(0.78, 1.0, flicker) * glitchAmt * 0.65;
    col *= (1.0 - flickAmt);

    // ══ 8. GRAIN ══════════════════════════════════════════════════════════
    float grain = (hash21(uv * vec2(317.0, 411.0) + floor(iTime * 60.0)) - 0.5)
                * 0.09 * glitchAmt;
    col += vec3(grain);

    fragColor = vec4(col, 1.0);
}
