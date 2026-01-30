#version 300 es
precision highp float;

// Hex Kaleidoscope Shader (Ashanoha)
// Created by coposuke (2020-01-24)
// https://www.shadertoy.com/view/wlGGWG

// Standard uniforms
uniform float iTime;
uniform vec2 iResolution;

// MQTT-controllable uniforms
uniform float speed;        // Animation speed (default: 1.0)
uniform float scale;        // Pattern scale (default: 1.0)
uniform float colorShift;   // Color shift offset (default: 0.0)
uniform float brightness;   // Overall brightness (default: 1.0)

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

#define PI  	3.14159265357989
#define TAU 	(PI * 2.0)
#define HEX_COS (0.86602540378443 * 0.5)
#define HEX_TAN (0.57735026918962 * 0.5)


struct Animation
{
    float screenAngle;
    float screenScale;
    vec2  screenOffset;
    float lineWidth;
    float lineColorOffset;
    float meshColorOffset;
    float meshColorDist;
    float lightAngle;
    float blendLine;
    float blendSolid;
    float blendMesh;
};


mat2 rotate(float angle)
{
    float s = sin(angle), c = cos(angle);
    return mat2(c, -s, s, c);
}

vec2 pmod(vec2 pos, float num, out float id)
{
    float angle = atan(pos.x, pos.y) + PI / num;
    float split = TAU / num;
    id = floor(angle / split);
	angle = id * split;
    return rotate(-angle) * pos;
}

float cubicInOut(float time)
{
  return (time < 0.5) ? (4.0 * time * time * time) : (1.0 - 4.0 * pow(1.0 - time, 3.0));
}

// for line
void map(vec2 uv, out vec3 near, out vec3 neighbor)
{
    vec2 point;
    near = vec3(1e+4);

    for(float y=-1.0; y<=1.0; y+=2.0)
    {
        point = vec2(0.0, HEX_COS + y * HEX_TAN * 0.25);
        float dist = distance(uv, point);
        near = near.z < dist ? near : vec3(point, dist);
    }

    for(float x=-1.0; x<=1.0; x+=2.0)
    {
	    for(float y=-1.0; y<=1.0; y+=2.0)
        {
            for(float both=-1.0; both<=1.0; both+=2.0)
            {
                point = vec2(x * 0.125, HEX_COS + y * HEX_COS * 0.5);
                point.x += both * 0.5     * 0.125 * -x;
                point.y += both * HEX_TAN * 0.125 * -y;
                float dist = distance(uv, point);
                near = near.z < dist ? near : vec3(point, dist);
            }
        }
    }

    neighbor = vec3(1e+4);

    for(float y=-1.0; y<=1.0; y+=2.0)
    {
        point = vec2(0.0, HEX_COS + y * HEX_TAN * 0.25);
        if(near.xy != point)
        {
            vec2 center = (point + near.xy) * 0.5;
            float dist = dot(uv - center, normalize(near.xy - point));
            neighbor = neighbor.z < dist ? neighbor : vec3(point, dist);
        }
    }

    for(float x=-1.0; x<=1.0; x+=2.0)
    {
	    for(float y=-1.0; y<=1.0; y+=2.0)
        {
            for(float both=-1.0; both<=1.0; both+=2.0)
            {
                point = vec2(x * 0.125, HEX_COS + y * HEX_COS * 0.5);
                point.x += both * 0.5     * 0.125 * -x;
                point.y += both * HEX_TAN * 0.125 * -y;

                if(near.xy != point)
                {
                    vec2 center = (point + near.xy) * 0.5;
                    float dist = dot(uv - center, normalize(near.xy - point));
                    neighbor = neighbor.z < dist ? neighbor : vec3(point, dist);
                }
            }
        }
    }
}

// for normal
vec4 normalmap(vec2 uv)
{
    vec2 point = vec2(0);
    vec3 near = vec3(1e+4);
    vec3 neighbor = vec3(1e+4);

    for(float y=-1.0; y<=1.0; y+=2.0)
    {
        point = vec2(0.0, HEX_COS + y * HEX_TAN * 0.5);
        float dist = distance(uv, point);
        near = near.z < dist ? near : vec3(point, dist);
    }

	for(float y=-1.0; y<=1.0; y+=2.0)
    {
        point = vec2(0.0, HEX_COS + y * HEX_TAN * 0.5);
        if(near.xy != point)
        {
            vec2 center = (point + near.xy) * 0.5;
            float dist = dot(uv - center, normalize(near.xy - point));
            neighbor = neighbor.z < dist ? neighbor : vec3(point, dist);
        }
    }

    for(float x=-1.0; x<=1.0; x+=2.0)
    {
	    for(float y=-1.0; y<=1.0; y+=2.0)
        {
            point = vec2(x * 0.25, HEX_COS - y * (HEX_COS - HEX_TAN * 0.5));
            vec2 center = (point + near.xy) * 0.5;
            float dist = dot(uv - center, normalize(near.xy - point));
            neighbor = neighbor.z < dist ? neighbor : vec3(point, dist);
        }
    }

    return vec4(normalize(vec3(neighbor.xy - near.xy, 1.0)), neighbor.z);
}

void animate(float time, vec2 uv, inout Animation anim)
{
    float animLoop = floor(floor(time) / 13.0);
    float animType = mod(floor(time), 13.0);
    float animTime = fract(time);
    float clockwise = mod(animLoop, 2.0) <= 0.0 ? 1.0 : -1.0;

    anim.screenScale = 2.0;
    anim.screenAngle = PI * 0.166667;
    anim.screenOffset= vec2(0, 0);
    anim.lineWidth   = 0.01;
    anim.lineColorOffset = 0.0;
    anim.meshColorOffset = 0.0;
    anim.meshColorDist = 200.0;
    anim.lightAngle = 0.0;
    anim.blendLine = 0.0;
    anim.blendMesh = 0.0;
    anim.blendSolid = 0.0;

    if(animType <= 0.0)
    {
        anim.screenScale = cubicInOut(animTime) * 1.0 + 1.0;
    	anim.lineWidth   = cubicInOut(1.0 - animTime) * 0.4 + 0.01;
    	anim.lineColorOffset = animTime;
    	anim.blendLine = 1.0;
    }
    else if(animType <= 1.0)
    {
        anim.screenScale -= animTime * 0.02;
    	anim.lineColorOffset = PI * 2.0 * animTime;
    	anim.blendLine = 1.0;
    }
    else if(animType <= 2.0)
    {
        anim.screenScale -= animTime * 0.02 + 0.02;
    	anim.lineColorOffset = PI * 2.0 * animTime;
        anim.meshColorOffset = PI * 3.0 * animTime;
    	anim.blendLine = smoothstep(1.0, 0.0, animTime);
    	anim.blendMesh = smoothstep(0.0, 1.0, animTime);
    }
    else if(animType <= 3.0)
    {
        anim.screenScale -= animTime * 0.02 + 0.04;
        anim.meshColorOffset = PI * 3.0 * animTime + PI;
    	anim.meshColorDist = smoothstep(1.0, 0.2, animTime) * 200.0;
   	 	anim.lightAngle  = PI * 2.0 * time;
    	anim.blendMesh = smoothstep(0.8, 0.2, animTime);
    	anim.blendSolid = smoothstep(0.0, 1.0, animTime);
    }
    else if(animType <= 4.0)
    {
        anim.screenScale -= animTime * 0.02 + 0.06;
    	anim.blendSolid = 1.0;
    }
    else if(animType <= 10.0)
    {
        animTime += animType - 5.0;
        anim.screenScale -= clamp(animTime * 0.02 + 0.08, 0.0, 0.1);
        animTime /= 11.0 - 5.0;
        anim.screenAngle += smoothstep(0.0, 1.0, animTime) * PI * 0.5 * clockwise;

        uv = rotate(PI * 2.0 * animTime * clockwise) * uv;
        float pos = abs(uv.x + 0.0) + animTime;
        float blend = smoothstep(-0.1, 0.0, sin(pos * PI * 3.0 * sin(animTime * PI)));
    	anim.blendSolid = blend;
        anim.blendLine = 1.0 - blend;
    	anim.lineColorOffset = PI * 2.0 * animTime;
    }
    else if(animType <= 11.0)
    {
        anim.screenScale -= 0.1;
        anim.screenAngle += PI * 0.5 * clockwise;
        anim.lightAngle += PI * 2.0 * animTime;
    	anim.blendSolid = 1.0;
    }
    else if(animType <= 12.0)
    {
        anim.screenScale -= 0.1;
        anim.screenAngle += PI * 0.5 * clockwise;
        anim.lightAngle += PI * 2.0 * animTime;

        float lineTime = (sin(animTime * PI * 3.0 - PI * 0.5) * 0.5 + 0.5);
        lineTime = lineTime * lineTime * (animTime - (uv.x * uv.y * 0.2));
        anim.lineWidth = clamp(lineTime, 0.0, 1.0) * 0.5;
        anim.blendLine = 1.0;
    	anim.blendSolid = 1.0;
    }
}


void mainImage( out vec4 fragColor_out, in vec2 fragCoord )
{
    vec2 uv = (fragCoord.xy * 2.0 - iResolution.xy) / min(iResolution.x, iResolution.y);

    // animation
    Animation anim;
    animate(iTime * speed, uv, anim);

    // view
    uv *= anim.screenScale / scale;
    uv += anim.screenOffset;
    uv = rotate(anim.screenAngle) * uv;

    // tiling
    vec2 uvLocal = uv;
    uvLocal.x = mod(uv.x, 1.0) - 0.5;
    uvLocal.y = mod(uv.y, HEX_COS * 2.0) - HEX_COS;

    // rot tiling
    float id;
    uvLocal = pmod(uvLocal, 6.0, id);

    // scene
    vec3 near, neighbor;
    map(uvLocal, near, neighbor);

    // lighting
    vec4 normal = normalmap(uvLocal);
    normal.xy = rotate(id * PI / 3.0) * normal.xy;
    float dist = normal.w;
    dist = 1.0 - pow(1.0 - dist, 20.0);

    vec3 lightDir = normalize(vec3(rotate(anim.lightAngle) * vec2(1,0), 0.25));
    float light = dot(normal.xyz, lightDir) * 0.8 + 0.2;

    // draw
    float lineWidth = (1.0 - smoothstep(0.0, anim.lineWidth, neighbor.z));
    vec3 lineColor = cos(vec3(0,2,4) * PI / 3.0 + anim.lineColorOffset + colorShift) * 0.25 + 1.0;
    vec3 meshColor = cos(vec3(0,2,4) * PI / 3.0 + anim.meshColorOffset + anim.meshColorDist * neighbor.z + colorShift) * 0.35 + 0.65;
    float solid = (dist * light) * 0.6 + 0.2;
    solid = 1.0 - pow(1.0 - solid, 3.0);

    fragColor_out.rgb = vec3(0);
    fragColor_out.rgb = mix(fragColor_out.rgb, vec3(solid), anim.blendSolid);
    fragColor_out.rgb = mix(fragColor_out.rgb, lineColor, lineWidth * anim.blendLine);
    fragColor_out.rgb = mix(fragColor_out.rgb, meshColor, anim.blendMesh);

    // apply brightness
    fragColor_out.rgb *= brightness;

    // degamma
    fragColor_out.rgb = pow(fragColor_out.rgb, vec3(1.0 / 2.2));
    fragColor_out.a = 1.0;
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
