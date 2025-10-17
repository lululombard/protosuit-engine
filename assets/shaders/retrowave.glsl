#version 300 es
precision highp float;

// Retrowave Shader with MQTT-controllable parameters

// Standard uniforms
uniform float iTime;
uniform vec2 iResolution;

// MQTT-controllable uniforms
uniform float speed;          // Animation speed (default: 1.0)
uniform float gridIntensity;  // Grid brightness (default: 1.0)
uniform float sunHeight;      // Sun Y position (default: 0.0)
uniform vec3 sunColor;        // Sun color (default: orange/pink)
uniform vec3 gridColor;       // Grid color (default: pink/purple)
uniform vec3 skyColor;        // Sky/horizon color (default: purple)
uniform vec3 mountainColor;   // Mountain/fuji color (default: blue/purple)

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

float sun(vec2 uv, float battery)
{
 	float val = smoothstep(0.3, 0.29, length(uv));
 	float bloom = smoothstep(0.7, 0.0, length(uv));
   float cut = 3.0 * sin((uv.y + iTime * 0.2 * (battery + 0.02)) * 100.0)
				+ clamp(uv.y * 14.0 + 1.0, -6.0, 6.0);
   cut = clamp(cut, 0.0, 1.0);
   return clamp(val * cut, 0.0, 1.0) + bloom * 0.6;
}

float grid(vec2 uv, float battery)
{
   vec2 size = vec2(uv.y, uv.y * uv.y * 0.2) * 0.01;
   uv += vec2(0.0, iTime * 4.0 * (battery + 0.05));
   uv = abs(fract(uv) - 0.5);
 	vec2 lines = smoothstep(size, vec2(0.0), uv);
 	lines += smoothstep(size * 5.0, vec2(0.0), uv) * 0.4 * battery;
   return clamp(lines.x + lines.y, 0.0, 3.0);
}

float dot2(in vec2 v ) { return dot(v,v); }

float sdTrapezoid( in vec2 p, in float r1, float r2, float he )
{
    vec2 k1 = vec2(r2,he);
    vec2 k2 = vec2(r2-r1,2.0*he);
    p.x = abs(p.x);
    vec2 ca = vec2(p.x-min(p.x,(p.y<0.0)?r1:r2), abs(p.y)-he);
    vec2 cb = p - k1 + k2*clamp( dot(k1-p,k2)/dot2(k2), 0.0, 1.0 );
    float s = (cb.x<0.0 && ca.y<0.0) ? -1.0 : 1.0;
    return s*sqrt( min(dot2(ca),dot2(cb)) );
}

float sdLine( in vec2 p, in vec2 a, in vec2 b )
{
    vec2 pa = p-a, ba = b-a;
    float h = clamp( dot(pa,ba)/dot(ba,ba), 0.0, 1.0 );
    return length( pa - ba*h );
}

float sdBox( in vec2 p, in vec2 b )
{
    vec2 d = abs(p)-b;
    return length(max(d,vec2(0))) + min(max(d.x,d.y),0.0);
}

float opSmoothUnion(float d1, float d2, float k){
	float h = clamp(0.5 + 0.5 * (d2 - d1) /k,0.0,1.0);
    return mix(d2, d1 , h) - k * h * ( 1.0 - h);
}

float sdCloud(in vec2 p, in vec2 a1, in vec2 b1, in vec2 a2, in vec2 b2, float w)
{
	//float lineVal1 = smoothstep(w - 0.0001, w, sdLine(p, a1, b1));
    float lineVal1 = sdLine(p, a1, b1);
    float lineVal2 = sdLine(p, a2, b2);
    vec2 ww = vec2(w*1.5, 0.0);
    vec2 left = max(a1 + ww, a2 + ww);
    vec2 right = min(b1 - ww, b2 - ww);
    vec2 boxCenter = (left + right) * 0.5;
    //float boxW = right.x - left.x;
    float boxH = abs(a2.y - a1.y) * 0.5;
    //float boxVal = sdBox(p - boxCenter, vec2(boxW, boxH)) + w;
    float boxVal = sdBox(p - boxCenter, vec2(0.04, boxH)) + w;

    float uniVal1 = opSmoothUnion(lineVal1, boxVal, 0.05);
    float uniVal2 = opSmoothUnion(lineVal2, boxVal, 0.05);

    return min(uniVal1, uniVal2);
}

void mainImage( out vec4 fragColor_out, in vec2 fragCoord )
{
    vec2 uv = (2.0 * fragCoord.xy - iResolution.xy)/iResolution.y;
    float battery = 1.0;  // Use speed uniform to control animation
    float timeScale = iTime * speed;

    // Grid
    float fog = smoothstep(0.1, -0.02, abs(uv.y + 0.2));
    vec3 col = skyColor * 0.5;  // Use sky color for background

    if (uv.y < -0.2)
    {
        // Ground grid section
        uv.y = 3.0 / (abs(uv.y + 0.2) + 0.05);
        uv.x *= uv.y * 1.0;
        float gridVal = grid(uv, battery) * gridIntensity;
        col = mix(col, gridColor, gridVal);
    }
    else
    {
        // Sky/sun/mountain section
        float fujiD = min(uv.y * 4.5 - 0.5, 1.0);
        uv.y -= battery * 1.1 - 0.51 + sunHeight;

        vec2 sunUV = uv;

        // Sun
        sunUV += vec2(0.75, 0.2);
        col = sunColor;
        float sunVal = sun(sunUV, battery);

        col = mix(col, sunColor * vec3(1.0, 0.6, 0.3), sunUV.y * 2.0 + 0.2);
        col = mix(vec3(0.0, 0.0, 0.0), col, sunVal);

        // Mountain (Fuji)
        float fujiVal = sdTrapezoid(uv + vec2(-0.75+sunUV.y * 0.0, 0.5), 1.75 + pow(uv.y * uv.y, 2.1), 0.2, 0.5);
        float waveVal = uv.y + sin(uv.x * 20.0 + timeScale * 2.0) * 0.05 + 0.2;
        float wave_width = smoothstep(0.0, 0.01, waveVal);

        // Mountain color
        col = mix(col, mix(mountainColor * 0.5, mountainColor, fujiD), step(fujiVal, 0.0));
        // Mountain top snow
        col = mix(col, gridColor, wave_width * step(fujiVal, 0.0));
        // Mountain outline
        col = mix(col, gridColor, 1.0 - smoothstep(0.0, 0.01, abs(fujiVal)));

        // Horizon color
        col += mix(col, mix(sunColor * vec3(1.0, 0.4, 1.0), skyColor, clamp(uv.y * 3.5 + 3.0, 0.0, 1.0)), step(0.0, fujiVal));

        // Clouds
        vec2 cloudUV = uv;
        cloudUV.x = mod(cloudUV.x + timeScale * 0.1, 4.0) - 2.0;
        float cloudTime = timeScale * 0.5;
        float cloudY = -0.5;
        float cloudVal1 = sdCloud(cloudUV,
                                 vec2(0.1 + sin(cloudTime + 140.5)*0.1, cloudY),
                                 vec2(1.05 + cos(cloudTime * 0.9 - 36.56) * 0.1, cloudY),
                                 vec2(0.2 + cos(cloudTime * 0.867 + 387.165) * 0.1, 0.25+cloudY),
                                 vec2(0.5 + cos(cloudTime * 0.9675 - 15.162) * 0.09, 0.25+cloudY), 0.075);
        cloudY = -0.6;
        float cloudVal2 = sdCloud(cloudUV,
                                 vec2(-0.9 + cos(cloudTime * 1.02 + 541.75) * 0.1, cloudY),
                                 vec2(-0.5 + sin(cloudTime * 0.9 - 316.56) * 0.1, cloudY),
                                 vec2(-1.5 + cos(cloudTime * 0.867 + 37.165) * 0.1, 0.25+cloudY),
                                 vec2(-0.6 + sin(cloudTime * 0.9675 + 665.162) * 0.09, 0.25+cloudY), 0.075);

        float cloudVal = min(cloudVal1, cloudVal2);

        col = mix(col, skyColor, 1.0 - smoothstep(0.075 - 0.0001, 0.075, cloudVal));
        col += vec3(1.0, 1.0, 1.0) * (1.0 - smoothstep(0.0, 0.01, abs(cloudVal - 0.075)));
    }

    col += fog * fog * fog;
    col = mix(vec3(col.r, col.r, col.r) * 0.5, col, battery * 0.7);

    fragColor_out = vec4(col, 1.0);
}

void main() {
    mainImage(fragColor, v_fragCoord);
}