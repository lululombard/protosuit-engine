#version 300 es
precision highp float;

// Absolute Solver Shader
// Original shader by Miggy

// --- Standard uniforms (provided by renderer) ---
uniform float iTime;
uniform vec2 iResolution;
uniform vec4 iMouse;

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 outColor;

// --- Uniforms (configurable via MQTT) ---
uniform vec3  gradBottom;      // Bottom gradient color (default: purple)
uniform vec3  gradTop;         // Top gradient color (default: yellow)
uniform float gradPower;       // Gradient curve power (>1 = compressed top, <1 = compressed bottom)
uniform vec3  bgColor;         // Background color
uniform float glitchIntensity; // Glitch intensity 0..1
uniform float glitchRate;      // Glitch burst frequency (higher = more frequent)
uniform float rotationSpeed;   // Logo rotation speed (0 = still)
uniform float headVariant;     // 0 = arrow heads, 1 = hex heads

// --- Glitch "cinématique" ---
// GLITCH_MODE : 0=OFF, 1=ON (bursts aléatoires), 2=ON tant que la souris est pressée
const int   GLITCH_MODE      = 1;
const float GLITCH_MARGIN    = 0.0; // marge de sécurité (évite que ça tape trop les bords)


// Get head variant (uses uniform, mouse override disabled since we control via interface)
int getHeadVariant() {
    return int(headVariant);
}



// --- Utilitaires ---
vec2 rotate(vec2 p, float a) {
    float c = cos(a), s = sin(a);
    return vec2(c*p.x - s*p.y,
                s*p.x + c*p.y);
}

// Hash rapides (sans textures)
float hash11(float p) {
    p = fract(p * 0.1031);
    p *= p + 33.33;
    p *= p + p;
    return fract(p);
}

float hash21(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

// Enveloppe de glitch : des "bursts" courts façon cinéma
// Enveloppe de glitch : bursts VRAIMENT aléatoires (pas de "hum" permanent)
// GLITCH_RATE = nombre de fenêtres par seconde (plus grand => on "tire" plus souvent)
// La proba de déclenchement est fixée ici (tu peux l'exposer si tu veux).
float glitchEnv(float t) {
    float seg = floor(t * glitchRate);
    float ft  = fract(t * glitchRate);

    // Proba de burst par fenêtre (ex: 0.10 = 10% des fenêtres déclenchent)
    float pBurst = 0.10;
    float trig = step(1.0 - pBurst, hash11(seg + 1.7));

    // Burst court : montée rapide, tenue brève, chute
    float up   = smoothstep(0.00, 0.05, ft);
    float hold = 1.0 - smoothstep(0.18, 0.55, ft);
    float env  = trig * up * hold;

    // Micro-spikes à l'intérieur du burst (donne le côté "cinéma")
    float spikes = step(0.65, hash11(seg * 13.0 + floor(ft * 24.0)));
    env *= 0.75 + 0.25 * spikes;

    return clamp(env, 0.0, 1.0);
}

float glitchEnable() {
    if (GLITCH_MODE == 0) return 0.0;
    if (GLITCH_MODE == 2) return (iMouse.z > 0.0) ? 1.0 : 0.0;
    return 1.0;
}

// Distorsion principale : déchirures horizontales + blocs + wobble
vec2 glitchWarp(vec2 u, vec2 uv01, float t, float g) {
    // u : coord centrée (normalisée par iResolution.y)
    // uv01 : [0..1]

    float env = glitchEnv(t) * g;
    if (env <= 0.0) return u;

    float seg = floor(t * glitchRate);
    float ft  = fract(t * glitchRate);

    // --- 0) "Frame jump" : toute l'image saute pendant quelques frames ---
    float jumpTrig = step(0.85, hash11(seg + 50.0));
    float jumpWin  = smoothstep(0.00, 0.06, ft) * (1.0 - smoothstep(0.12, 0.22, ft));
    vec2  jumpOff  = (vec2(hash11(seg + 51.0), hash11(seg + 52.0)) - 0.5) * vec2(0.08, 0.04);
    jumpOff *= env * jumpTrig * jumpWin;

    // --- 1) SLICES : image "hachée" en bandes horizontales décalées ---
    float sliceN = mix(10.0, 40.0, hash11(seg + 20.0));
    float sid    = floor(uv01.y * sliceN);
    float sr     = hash11(sid + seg * 97.0);
    float sOn    = step(0.55, sr); // toutes les bandes ne bougent pas
    float sAmt   = (sr - 0.5) * 0.22 * env * sOn; // gros effet "mauvais endroit"

    // Petites ruptures verticales (genre "frame tear")
    float notch = step(0.92, hash11(sid + seg * 131.0));
    float sY    = (hash11(sid + seg * 19.0) - 0.5) * 0.03 * env * notch;

    // --- 2) Déchirure localisée (bande qui glisse) ---
    float y0  = hash11(seg + 10.0);
    float bw  = mix(0.010, 0.045, hash11(seg + 11.0));
    float band = smoothstep(y0 - bw, y0, uv01.y) - smoothstep(y0, y0 + bw, uv01.y);
    float tear = (hash11(seg + 12.0) - 0.5) * 0.18 * env;

    // --- 3) Blocs (macro) ---
    vec2 cell = floor(uv01 * vec2(18.0, 8.0));
    float cr  = hash21(cell + seg * vec2(3.1, 7.7));
    float on  = step(0.88, cr) * env;
    vec2  bo  = (vec2(hash11(cr + 1.0), hash11(cr + 2.0)) - 0.5);
    bo *= vec2(0.060, 0.025) * on;

    // --- 4) Wobble très subtil (uniquement pendant burst) ---
    float wob = sin((uv01.y * 90.0) + t * 28.0) * 0.0015 * env;

    vec2 off;
    off.x = sAmt + tear * band + bo.x + wob;
    off.y = sY + bo.y;

    return u + jumpOff + off;
}

// Smooth union (fillet) entre deux SDF
float smin(float a, float b, float k) {
    float h = clamp(0.5 + 0.5*(b - a)/k, 0.0, 1.0);
    return mix(b, a, h) - k*h*(1.0 - h);
}

// Hexagone SDF (IQ) – pointy-top (sommet en haut)
float sdHex(vec2 p, float r) {
    const vec3 k = vec3(-0.866025404, 0.5, 0.577350269); // (-√3/2, 1/2, 1/√3)
    p = abs(p);
    p -= 2.0 * min(dot(k.xy, p), 0.0) * k.xy;
    p -= vec2(clamp(p.x, -k.z*r, k.z*r), r);
    return length(p) * sign(p.y);
}

// Trapezoïde vertical centré (IQ). r1 = demi-largeur en bas (p.y < 0), r2 = demi-largeur en haut (p.y > 0)
float sdTrapezoid(vec2 p, float r1, float r2, float he) {
    vec2 k1 = vec2(r2, he);
    vec2 k2 = vec2(r2 - r1, 2.0*he);

    p.x = abs(p.x);

    // distance aux "caps" horizontaux
    vec2 ca = vec2(p.x - min(p.x, (p.y < 0.0) ? r1 : r2), abs(p.y) - he);

    // distance aux côtés inclinés
    vec2 cb = p - k1 + k2 * clamp( dot(k1 - p, k2) / dot(k2, k2), 0.0, 1.0 );

    float s = (cb.x < 0.0 && ca.y < 0.0) ? -1.0 : 1.0;
    return s * sqrt( min(dot(ca, ca), dot(cb, cb)) );
}

// Trapezoïde arrondi (rayon rr) : on "shrink" puis on offset
float sdRoundedTrapezoid(vec2 p, float r1, float r2, float he, float rr) {
    // Evite les valeurs négatives si rr est trop grand
    r1 = max(r1 - rr, 0.0);
    r2 = max(r2 - rr, 0.0);
    he = max(he - rr, 0.0);
    return sdTrapezoid(p, r1, r2, he) - rr;
}

// Petit "module" hex : anneau + hex plein au centre (comme ton hex principal)
float sdHexModule(vec2 p, float rInner, float rHole, float rOuter) {
    float dInner = sdHex(p, rInner);
    float dRing  = max(sdHex(p, rOuter), -sdHex(p, rHole));
    return min(dInner, dRing);
}


// Une tige = trapezoïde évasé (plus large côté hex), avec coins arrondis
float sdShaftLocal(vec2 p, float y0, float y1, float wBase, float wTip, float rr) {
    float yMid = 0.5*(y0 + y1);
    float he   = 0.5*(y1 - y0);
    vec2 q = p - vec2(0.0, yMid);

    // r1 = bas (vers l'hex), r2 = haut (vers la flèche)
    return sdRoundedTrapezoid(q, wBase, wTip, he, rr);
}

// --- Têtes : deux variantes ---
// Variante A : flèche (triangle arrondi)
float sdArrowHeadLocal(vec2 p, float yBase, float yTip,
                       float wBase, float rr) {

    float yMid = 0.5*(yBase + yTip);
    float he   = 0.5*(yTip - yBase);
    vec2  q    = p - vec2(0.0, yMid);

    return sdRoundedTrapezoid(q, wBase, 0.0, he, rr);
}

float sdThreeArrowHeads(vec2 p, float yBase, float yTip,
                        float wBase, float rr,
                        float rotOffset) {
    const float TAU = 6.28318530718;
    const float A   = TAU/3.0;

    vec2 q0 = rotate(p, rotOffset);
    vec2 q1 = rotate(p, rotOffset + A);
    vec2 q2 = rotate(p, rotOffset - A);

    float d0 = sdArrowHeadLocal(q0, yBase, yTip, wBase, rr);
    float d1 = sdArrowHeadLocal(q1, yBase, yTip, wBase, rr);
    float d2 = sdArrowHeadLocal(q2, yBase, yTip, wBase, rr);

    return min(d0, min(d1, d2));
}

// Variante B : petit hexagone au bout (anneau + hex interne)
// Variante B : petit hexagone au bout (anneau + hex interne)
// On expose séparément : anneau, trou, inner-fill.
float sdHexOuterRingLocal(vec2 p, float yCenter,
                          float rHole, float rOuter,
                          float hexRot) {
    vec2 q = p - vec2(0.0, yCenter);
    q = rotate(q, hexRot);
    return max(sdHex(q, rOuter), -sdHex(q, rHole));
}

float sdHexHoleLocal(vec2 p, float yCenter,
                     float rHole,
                     float hexRot) {
    vec2 q = p - vec2(0.0, yCenter);
    q = rotate(q, hexRot);
    return sdHex(q, rHole);
}

float sdHexInnerLocal(vec2 p, float yCenter,
                      float rInner,
                      float hexRot) {
    vec2 q = p - vec2(0.0, yCenter);
    q = rotate(q, hexRot);
    return sdHex(q, rInner);
}

float sdThreeHexOuterRings(vec2 p, float yCenter,
                           float rHole, float rOuter,
                           float rotOffset, float hexRot) {
    const float TAU = 6.28318530718;
    const float A   = TAU/3.0;

    vec2 q0 = rotate(p, rotOffset);
    vec2 q1 = rotate(p, rotOffset + A);
    vec2 q2 = rotate(p, rotOffset - A);

    float d0 = sdHexOuterRingLocal(q0, yCenter, rHole, rOuter, hexRot);
    float d1 = sdHexOuterRingLocal(q1, yCenter, rHole, rOuter, hexRot);
    float d2 = sdHexOuterRingLocal(q2, yCenter, rHole, rOuter, hexRot);

    return min(d0, min(d1, d2));
}

float sdThreeHexHoles(vec2 p, float yCenter,
                      float rHole,
                      float rotOffset, float hexRot) {
    const float TAU = 6.28318530718;
    const float A   = TAU/3.0;

    vec2 q0 = rotate(p, rotOffset);
    vec2 q1 = rotate(p, rotOffset + A);
    vec2 q2 = rotate(p, rotOffset - A);

    float d0 = sdHexHoleLocal(q0, yCenter, rHole, hexRot);
    float d1 = sdHexHoleLocal(q1, yCenter, rHole, hexRot);
    float d2 = sdHexHoleLocal(q2, yCenter, rHole, hexRot);

    return min(d0, min(d1, d2));
}

float sdThreeHexInners(vec2 p, float yCenter,
                       float rInner,
                       float rotOffset, float hexRot) {
    const float TAU = 6.28318530718;
    const float A   = TAU/3.0;

    vec2 q0 = rotate(p, rotOffset);
    vec2 q1 = rotate(p, rotOffset + A);
    vec2 q2 = rotate(p, rotOffset - A);

    float d0 = sdHexInnerLocal(q0, yCenter, rInner, hexRot);
    float d1 = sdHexInnerLocal(q1, yCenter, rInner, hexRot);
    float d2 = sdHexInnerLocal(q2, yCenter, rInner, hexRot);

    return min(d0, min(d1, d2));
}


// (Compat) ancien nom : on garde, mais on redirige vers la variante flèche.
float sdThreeHeads(vec2 p, float yBase, float yTip,
                   float wBase, float rr,
                   float rotOffset) {
    return sdThreeArrowHeads(p, yBase, yTip, wBase, rr, rotOffset);
}

// 3 tiges à 120°, avec un angle d'offset pour caler pile sur l'hex
float sdThreeShafts(vec2 p, float y0, float y1, float wBase, float wTip, float rr, float rotOffset) {
    const float TAU = 6.28318530718;
    const float A   = TAU/3.0; // 120°

    // Pour orienter les bras sans te battre : rotOffset = 0 => une tige pile verticale.
    vec2 q0 = rotate(p, rotOffset);
    vec2 q1 = rotate(p, rotOffset + A);
    vec2 q2 = rotate(p, rotOffset - A);

    float d0 = sdShaftLocal(q0, y0, y1, wBase, wTip, rr);
    float d1 = sdShaftLocal(q1, y0, y1, wBase, wTip, rr);
    float d2 = sdShaftLocal(q2, y0, y1, wBase, wTip, rr);

    return min(d0, min(d1, d2));
}

void mainImage(out vec4 fragColor, in vec2 fragCoord) {

    // Coord normalisées [0..1] (pratique pour scanlines)
    vec2 uv01 = fragCoord / iResolution.xy;

    // Coordonnées centrées, aspect correct (u en "unités écran" ~ [-0.5,0.5])
    vec2 u = (fragCoord - 0.5 * iResolution.xy) / iResolution.y;

    // Glitch warp (avant tout)
    float g = glitchEnable() * glitchIntensity;
    if (g > 0.0) {
        u = glitchWarp(u, uv01, iTime, g);
    }


    // Choix de variante AVANT le scale, pour pouvoir fitter automatiquement
    int headVariant = getHeadVariant();

    // --- Auto-fit dans un carré (utile pour 720x720) ---
    // On estime un rayon max du logo en espace "p" (tes unités SDF), puis on choisit un scale
    // tel que le logo tienne dans l'écran avec une marge.
    float margin = max(0.02, GLITCH_MARGIN); // marge (augmente si tu actives un gros glitch)

    // (Ces paramètres doivent rester cohérents avec ceux plus bas)
    float rOuter_fit = 0.19;
    float yEnd_fit   = 0.56;

    // Variante flèche
    float headRR_fit   = 0.020;
    float yHeadTip_fit = yEnd_fit + 0.300;

    // Variante hex
    float nodeOuter_fit  = 0.114;
    float yNodeCenter_fit = yEnd_fit + nodeOuter_fit * 0.95;

    // IMPORTANT : on veut une taille IDENTIQUE entre les variantes.
    // Donc on fit sur le pire cas (le plus grand encombrement) des 2 variantes.
    float armMaxArrow = (yHeadTip_fit + headRR_fit);
    float armMaxHex   = (yNodeCenter_fit + nodeOuter_fit);
    float rMax = max(rOuter_fit, max(armMaxArrow, armMaxHex));

    // scale grand => forme plus petite à l'écran (car p = u * scale)
    float scale = rMax / max(0.5 - margin, 1e-4);

    // Paramètre de réglage manuel (1.0 = auto-fit pur)
    float userFit = 1.00;

    vec2 p = u * scale * userFit;

    // --- ALIGNEMENT ---
    // On sépare la rotation du logo (global) de l'alignement relatif hex <-> tiges.
    float globalRot = rotationSpeed * iTime;  // rotation globale du logo (animée)
    vec2 pr = rotate(p, globalRot);

    float shaftRot = 0.0;                  // on veut la 1ère tige pile verticale
    vec2 pS = rotate(pr, shaftRot);

    float hexRot = 0.5235987756;           // pi/6 : aligne un sommet du hex avec la tige
    vec2 pH = rotate(pr, hexRot);

    // --- Hex central (tes paramètres) ---
    float rInner = 0.14;
    float rHole  = 0.16;
    float rOuter = 0.19;

    float dInner = sdHex(pH, rInner);

    float dRing = max(
        sdHex(pH, rOuter),
       -sdHex(pH, rHole)
    );

    float d = min(dInner, dRing);

    // --- Tiges (SANS les pointes) ---
    // Analyse de la référence : la tige est évasée (plus large côté hex) + coins doux.
    // Et la jonction avec l'hex est "fillet" (congé) => on fait une smooth-union.

    float yStart = rOuter + 0.006; // démarre LÉGÈREMENT hors de l’anneau : évite que la tige "mange" le sommet
    float yEnd   = 0.56;           // fin avant la tête de flèche

    float wBase  = 0.030; // demi-largeur côté hex (évasé)
    float wTip   = 0.012; // demi-largeur côté flèche
    float rr     = 0.006; // arrondi des coins de la tige

    // 0.0 => une tige verticale.
    // Si ton hex paraît tourné, ne touche pas ici : touche plutôt globalRot.
    float rotOffset = 0.0;

    float dShafts = sdThreeShafts(pS, yStart, yEnd, wBase, wTip, rr, rotOffset);

    // Empêche la tige d'empiéter vers l'intérieur (au-delà de l'arête interne de l'anneau)
    // => la tige ne peut exister que dans la zone "extérieur du hex de rayon rHole".
    float dOutsideInnerEdge = -sdHex(pH, rHole);
    dShafts = max(dShafts, dOutsideInnerEdge);

    // Congé à la jonction hex <-> tiges
    float kFillet = 0.018;
    d = smin(d, dShafts, kFillet);

    // --- Têtes (toggle) ---
    // Variante A : flèche (triangle)
    float headBase = 0.120;     // demi-largeur à la base
    float headRR   = 0.020;     // arrondi global
    float yHeadBase = yEnd - 0.00;
    float yHeadTip  = yEnd + 0.300;
    float dHeadsArrow = sdThreeArrowHeads(pS, yHeadBase, yHeadTip,
                                         headBase, headRR,
                                         rotOffset);

    // Variante B : petit hex au bout
    float nodeOuter = 0.114;          // rayon extérieur
    float nodeHole  = 0.095;         // trou (crée le trait noir)
    float nodeInner = 0.078;          // hex plein interne

    // Centre du petit hex : légèrement au-dessus de la fin de tige
    float yNodeCenter = yEnd + nodeOuter * 0.95;

    float dHeadsHexRing  = sdThreeHexOuterRings(pS, yNodeCenter,
                                            nodeHole, nodeOuter,
                                            rotOffset, hexRot);

    float dHeadsHexHole  = sdThreeHexHoles(pS, yNodeCenter,
                                          nodeHole,
                                          rotOffset, hexRot);

    float dHeadsHexInner = sdThreeHexInners(pS, yNodeCenter,
                                           nodeInner,
                                           rotOffset, hexRot);

    // Choix de variante (déjà calculé plus haut via getHeadVariant)
    float dHeads = (headVariant == 0) ? dHeadsArrow : dHeadsHexRing;

    // Raccord tête <-> tige : plus accentué que hex <-> tige
    float kHeadArrow = 0.130;
    float kHeadHex   = 0.040; // plus petit : évite que le congé remplisse le "trou" du module hex
    float kHead = (headVariant == 0) ? kHeadArrow : kHeadHex;

    d = smin(d, dHeads, kHead);

    // IMPORTANT (variante hex) : le smooth-union peut "remplir" la gorge (le trou) du module.
    // On resoustrait le trou APRÈS la jonction, puis on ré-ajoute l'hex interne sans smooth.
    if (headVariant == 1) {
        d = max(d, -dHeadsHexHole);   // creuse la gorge
        d = min(d, dHeadsHexInner);   // remet l'hex plein interne
    }

    // Antialiasing
    float aa = fwidth(d);
    float a = smoothstep(aa, -aa, d);

    // --- Post glitch (flicker / scanlines / grain) ---
    float env = glitchEnv(iTime) * glitchEnable() * glitchIntensity;

    // Flicker global (léger)
    float flick = 1.0 - 0.15 * env * (0.5 + 0.5 * sin(iTime * 42.0 + 6.2831 * hash11(floor(iTime))));

    // Scanlines (subtiles)
    float scan = 1.0 - 0.10 * env * (0.5 + 0.5 * sin(uv01.y * 720.0 + iTime * 35.0));

    // Grain temporel
    float gr = hash21(floor(fragCoord) + floor(iTime * 60.0));
    float grain = (gr - 0.5) * 0.10 * env;

    float mask = clamp(a * flick * scan + grain, 0.0, 1.0);

    // Dégradé vertical (bas->haut). On le calcule en uv01 (stable même si u est glitché).
    float gt = pow(clamp(uv01.y, 0.0, 1.0), gradPower);
    vec3 grad = mix(gradBottom, gradTop, gt);

    vec3 rgb = mix(bgColor, grad, mask);
    fragColor = vec4(rgb, 1.0);
}

void main() {
    mainImage(outColor, v_fragCoord);
}
