#version 300 es
precision highp float;

// Outer Wilds Solar System
// Created by Miolith (2024-01-02)
// https://www.shadertoy.com/view/lcXGWs

// Uniforms from moderngl
uniform float iTime;
uniform vec2 iResolution;
uniform int iFrame;

// Custom uniforms for interactive control
uniform float cameraX;         // Camera X rotation (-3.14 to 3.14)
uniform float cameraY;         // Camera Y rotation (-3.14 to 3.14)
uniform float cameraDistance;  // Camera distance from origin (2.0-8.0)
uniform float timeSpeed;       // Time speed multiplier (0.1-3.0)
uniform float sunIntensity;    // Sun brightness (0.1-2.0)
uniform float backgroundStars; // Background star density (0.0-2.0)

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

#define PI 3.14159265
#define TWO_PI 6.28318531

#define DEGREES_180 3.14159265
#define DEGREES_90 1.57079633

#define TIME_OFFSET 20.0
#define TIME ((iTime * 0.5 * timeSpeed) + TIME_OFFSET)  // Use uniform for speed control

#define SUN_COLOR_INDEX 0
#define SUN_STATION_COLOR_INDEX 1
#define EMBER_TWIN_COLOR_INDEX 2
#define ASH_TWIN_COLOR_INDEX 3
#define TIMBER_HEARTH_COLOR_INDEX 4
#define ATTLEROCK_COLOR_INDEX 5
#define BRITTLE_HOLLOW_COLOR_INDEX 6
#define HOLLOW_BLACK_HOLE_COLOR_INDEX 7
#define HOLLOWS_LANTERN_COLOR_INDEX 8
#define GIANTS_DEEP_COLOR_INDEX 9
#define DARK_BRAMBLE_COLOR_INDEX 10
#define INTERLOPER_COLOR_INDEX 11
#define WHITE_HOLE_COLOR_INDEX 12

struct VFXObj
{
    vec3 color;
    float opacity;
    float dist;
};

struct Obj
{
    int color_index;
    float dist;
    vec3 relative_pos;
};

mat2x2 rotation(float angle)
{
    float c = cos(angle);
    float s = sin(angle);
    return mat2(
        c, -s,
        s, c
    );
}

float hash(float p) { p = fract(p * 0.011); p *= p + 7.5; p *= p + p; return fract(p); }

float noise3d(vec3 x) {
    const vec3 step = vec3(110, 241, 171);

    vec3 i = floor(x);
    vec3 f = fract(x);

    float n = dot(i, step);

    vec3 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix( hash(n + dot(step, vec3(0, 0, 0))), hash(n + dot(step, vec3(1, 0, 0))), u.x),
                   mix( hash(n + dot(step, vec3(0, 1, 0))), hash(n + dot(step, vec3(1, 1, 0))), u.x), u.y),
               mix(mix( hash(n + dot(step, vec3(0, 0, 1))), hash(n + dot(step, vec3(1, 0, 1))), u.x),
                   mix( hash(n + dot(step, vec3(0, 1, 1))), hash(n + dot(step, vec3(1, 1, 1))), u.x), u.y), u.z);
}

float smin( float a, float b)
{
    float k = 0.05;
    float h = clamp( 0.5+0.5*(b-a)/k, 0.0, 1.0 );
    return mix( b, a, h ) - k*h*(1.0-h);
}

float sdVerticalCapsule( vec3 p, float h, float r )
{
    p.y -= clamp( p.y, 0.0, h );
    return length( p ) - r;
}

float sdCone( vec3 p, vec2 c, float h )
{
    float q = length(p.xz);
    return max(dot(c.xy,vec2(q,p.y)),-h-p.y);
}

float sdRoundCone( vec3 p, float r1, float r2, float h )
{
    float b = (r1-r2)/h;
    float a = sqrt(1.0-b*b);

    vec2 q = vec2( length(p.xz), p.y );
    float k = dot(q,vec2(-b,a));
    if( k<0.0 ) return length(q) - r1;
    if( k>a*h ) return length(q-vec2(0.0,h)) - r2;
    return dot(q, vec2(a,b) ) - r1;
}

vec2 ellipseRot(vec2 pos, float angle, vec2 distances)
{
    pos.x += cos(angle) * distances.x;
    pos.y += sin(angle) * distances.y;
    return pos;
}

Obj closestObject(in Obj obj1, in Obj obj2)
{
    if (obj1.dist < obj2.dist)
        return obj1;
    return obj2;
}

VFXObj closestObject(in VFXObj obj1, in VFXObj obj2)
{
    if (obj1.dist < obj2.dist)
        return obj1;
    return obj2;
}

float rand(vec2 p)
{
	p+=.2127+p.x+.3713*p.y;
	vec2 r=4.789*sin(789.123*(p));
	return fract(r.x*r.y);
}

float noise(vec2 p)
{
	vec2 i=floor(p-.5);
	vec2 f=fract(p-.5);
	f = f*f*f*(f*(f*6.0-15.0)+10.0);
	float rt=mix(rand(i),rand(i+vec2(1.,0.)),f.x);
	float rb=mix(rand(i+vec2(0.,1.)),rand(i+vec2(1.,1.)),f.x);
	return mix(rt,rb,f.y);
}

float sphereSdf(vec3 pos, float radius)
{
    return length(pos) - radius;
}

Obj sun(vec3 pos)
{
    vec3 sphere_pos = pos;
    sphere_pos.xz *= rotation(-TIME *0.01);

    float waves = 0.015
                 * sin(pos.x * 20.0 + TIME)
                 * sin(pos.y * 20.0  + TIME)
                 * sin(pos.z * 20.0  + TIME);

    float radius = 0.4 + waves;

    float dist = sphereSdf(sphere_pos, radius);

    return Obj(SUN_COLOR_INDEX, dist, sphere_pos);
}

Obj sunStation(vec3 pos)
{
    vec3 sphere_pos = pos;

    float radius = 0.4;
    sphere_pos.yz *= rotation(-TIME);
    sphere_pos += vec3(0.0, 0.45, 0.0);
    float dist = sdCone(sphere_pos, vec2(sin(1.2), cos(1.2)), 0.08);
    sphere_pos.x -= 0.05;
    float dist2 = sdCone(sphere_pos, vec2(sin(1.1), cos(1.1)), 0.06);

    dist = min(dist, dist2);

    return Obj(SUN_STATION_COLOR_INDEX, dist, sphere_pos);
}

Obj hourglassTwins(vec3 pos)
{
    vec3 ash_pos = pos;
    ash_pos.xy *= rotation(-TIME);
    ash_pos += vec3(0.0, 0.6, 0.0);
    ash_pos.xz *= rotation(TIME);
    float black_dist = sphereSdf(ash_pos, 0.09);
    vec3 black_color = vec3(1.000,0.871,0.220);

    vec3 ember_pos = pos;
    ember_pos.xy = rotation(TIME) * ember_pos.xy;
    ember_pos += vec3(0.0, 0.85, 0.0);
    float radius = (abs(ember_pos.x) > 0.015) ? 0.11 : 0.08;
    float ember_dist = sphereSdf(ember_pos, radius);

    Obj final = closestObject(
        Obj(ASH_TWIN_COLOR_INDEX, black_dist, ash_pos),
        Obj(EMBER_TWIN_COLOR_INDEX, ember_dist, ember_pos)
    );

    vec3 sand_pos = pos;
    sand_pos.xy = rotation(TIME) * sand_pos.xy;
    sand_pos += vec3(0.0, 0.8, 0.0);
    float sand_dist = sdVerticalCapsule(sand_pos, 0.25, 0.02);


    return closestObject(
        final,
        Obj(ASH_TWIN_COLOR_INDEX, sand_dist, sand_pos)
    );
}

Obj timberHearth(vec3 pos)
{
    const float distance_from_sun = 1.2;
    const float size = 0.1;

    vec3 sphere_pos = pos;
    sphere_pos.xy *= rotation(-TIME/1.2);
    sphere_pos += vec3(0.0, 1.2, 0.0);
    vec3 planet_pos = sphere_pos;
    planet_pos.yz *= rotation(-TIME/1.5);
    float dist = sphereSdf(planet_pos, 0.10);

    vec3 plant_pos = planet_pos;
    float sand_dist = sdVerticalCapsule(plant_pos, 0.105, 0.02);
    dist = smin(dist, sand_dist);

    vec3 moon_pos = sphere_pos;
    moon_pos.xy += vec2(0.0, 0.2) * rotation(-TIME*2.0);
    float moon_dist = sphereSdf(moon_pos, 0.02);

    return closestObject(
        Obj(ATTLEROCK_COLOR_INDEX, moon_dist, moon_pos),
        Obj(TIMBER_HEARTH_COLOR_INDEX, dist, sphere_pos)
    );
}

Obj brittleHollow(vec3 pos)
{
    const float distance_from_sun = 1.5;
    const float size = 0.1;

    vec3 sphere_pos = pos;
    sphere_pos.xy *= rotation(-TIME/distance_from_sun);
    sphere_pos.y += distance_from_sun;
    float dist = abs(sphereSdf(sphere_pos, 0.1)) - 0.01;

    dist = max(-sphereSdf(sphere_pos - vec3(0.1,0.0,0.0), 0.05), dist);

    float black_hole_dist = sphereSdf(sphere_pos, 0.05);

    vec3 moon_pos = sphere_pos;
    moon_pos.xy += vec2(0.0, 0.2) * rotation(TIME);
    float moon_dist = sphereSdf(moon_pos, 0.02);

    return closestObject(
        Obj(HOLLOWS_LANTERN_COLOR_INDEX, moon_dist, moon_pos),
        closestObject(
            Obj(BRITTLE_HOLLOW_COLOR_INDEX, dist, sphere_pos),
            Obj(HOLLOW_BLACK_HOLE_COLOR_INDEX, black_hole_dist, sphere_pos)
        )
    );
}

Obj giantsDeep(vec3 pos)
{
    const float distance_from_sun = 2.1;
    const float size = 0.25;

    vec3 sphere_pos = pos;
    sphere_pos.xy *= rotation(-TIME/distance_from_sun);
    sphere_pos.y += distance_from_sun;
    float dist = sphereSdf(sphere_pos, 0.25);

    return Obj(GIANTS_DEEP_COLOR_INDEX, dist, sphere_pos);
}

Obj darkBramble(vec3 pos)
{
    vec3 sphere_pos = pos;
    sphere_pos.xy *= rotation(-TIME/2.8);
    sphere_pos += vec3(0.0, 2.8, 0.0);
    float dist = sphereSdf(sphere_pos, 0.09);

    // Simplified - only 3 tentacles instead of 6 for performance
    vec3 plant_pos = sphere_pos;

    plant_pos.xy *= rotation(-DEGREES_90);
    plant_pos.xz += 0.1 * vec2(cos(plant_pos.y * 12.0), sin(plant_pos.y*10.0));
    float sand_dist = sdVerticalCapsule(plant_pos, 0.30, 0.01);
    dist = min(dist, sand_dist);

    plant_pos = sphere_pos;
    plant_pos.xy *= rotation(DEGREES_90);
    plant_pos.xz += -0.1 * vec2(cos(plant_pos.y * 12.0), sin(plant_pos.y*10.0));
    sand_dist = sdVerticalCapsule(plant_pos, 0.30, 0.01);
    dist = min(dist, sand_dist);

    plant_pos = sphere_pos;
    plant_pos.yz *= rotation(-DEGREES_90);
    plant_pos.xz += -0.05 * vec2(cos(plant_pos.y * 12.0 + 1.0), sin(plant_pos.y*10.0 + 1.0));
    sand_dist = sdVerticalCapsule(plant_pos, 0.30, 0.01);
    dist = min(dist, sand_dist);

    dist *= 0.25;

    return Obj(DARK_BRAMBLE_COLOR_INDEX, dist, sphere_pos);
}

Obj theInterloper(vec3 pos)
{
    const float size = 0.06;

    vec3 sphere_pos = pos;
    sphere_pos.xy = ellipseRot(
        sphere_pos.xy + vec2(-1.3, 0.0),
        TIME+sin(TIME)*0.5,
        vec2(2.0, 0.7)
    );
    sphere_pos.xy *= rotation(-TIME - DEGREES_90);
    float sphere_dist = sphereSdf(sphere_pos, size);
    float dist = smin(sphere_dist,
                sphere_dist + 0.03
                * (sphere_pos.x > 0. ? 1. : 0.)
                * sin(sphere_pos.y * 60.0)
                * sin(sphere_pos.z * 70.0));

    return Obj(INTERLOPER_COLOR_INDEX, dist, sphere_pos);
}

Obj whiteHole(vec3 pos)
{
    const float size = 0.02;

    vec3 planet_pos = pos;
    planet_pos += vec3(2.4, -2.4, 0.0);
    float dist = sphereSdf(planet_pos, size);

    return Obj(WHITE_HOLE_COLOR_INDEX, dist, planet_pos);
}

VFXObj InterloperVFX(vec3 pos)
{
    const float size = 0.06;

    vec3 sphere_pos = pos;
    sphere_pos.xy = ellipseRot(
        sphere_pos.xy + vec2(-1.3, 0.0),
        TIME+sin(TIME)*0.5,
        vec2(2.0, 0.7)
    );
    sphere_pos.xy *= rotation(-TIME);
    sphere_pos.y -= 0.09;
    float dist = sdRoundCone(sphere_pos, 0.09, 0.01, 0.4);

    vec3 color = vec3(0.659,0.851,1.000);
    sphere_pos.y += 0.09;
    float opacity = exp(-length(sphere_pos)*4.0 + 0.5);

    return VFXObj(color, opacity, dist);
}

VFXObj VFX(vec3 ray_pos)
{
    return InterloperVFX(ray_pos);
}

Obj scene(vec3 ray_pos)
{
    Obj objects = closestObject(sun(ray_pos), hourglassTwins(ray_pos));
    objects = closestObject(objects, sunStation(ray_pos));
    objects = closestObject(objects, timberHearth(ray_pos));
    objects = closestObject(objects, brittleHollow(ray_pos));
    objects = closestObject(objects, giantsDeep(ray_pos));
    //objects = closestObject(objects, darkBramble(ray_pos));
    objects = closestObject(objects, theInterloper(ray_pos));
    objects = closestObject(objects, whiteHole(ray_pos));

    return objects;
}

vec3 emberTwinColor() { return vec3(1.000,0.596,0.220); }

vec3 ashTwinColor() { return vec3(1.000,0.871,0.220); }

vec3 sunColor(vec3 relative_pos)
{
    vec3 color1 = vec3(1.000,0.494,0.220);
    vec3 color2 = vec3(1.000,0.671,0.102);

    return mix(
        color1,
        color2,
        smoothstep(0.8, 0.0, noise3d(relative_pos*20. +TIME*0.2))
    );
}

vec3 sunStationColor() { return vec3(0.388,0.212,0.212); }

vec3 timberHearthColor() { return vec3(0.196,0.404,0.275); }

vec3 attleRockColor() { return vec3(0.612,0.612,0.612); }

vec3 brittleHollowColor(vec3 relative_pos)
{
    vec3 color1 = vec3(0.282,0.282,0.439);
    vec3 color2 = vec3(0.788,0.788,0.788);

    float color_rate = smoothstep(0.05, 0.045, length(relative_pos - vec3(0.0, 0.0, -0.1)));
    return mix(color1, color2, color_rate);
}

vec3 hollowBlackHoleColor(vec3 relative_pos)
{
    vec3 black_hole_color = vec3(0.000,0.000,0.000);
    vec3 border_color = vec3(1.000,0.400,0.000);

    float border = smoothstep(0.05, 0.052, length(relative_pos));

    return mix(black_hole_color, border_color, border);
}

vec3 hollowLanternColor() { return vec3(1.000,0.702,0.420); }

vec3 giantsDeepColor(vec3 relative_pos)
{
    vec3 color1 = vec3(0.196,0.376,0.180);
    vec3 color2 = vec3(0.196,0.384,0.314);

    vec3 color = mix(color1, color2,0.5 + 0.5*sin((relative_pos.y+relative_pos.x)*40.0));

    float period1 = min(1.0, mod(TIME*0.8, 6.11));
    float period2 = min(1.0, mod(TIME*0.8+0.5, 4.11));
    float lightning_frequency = max(
            smoothstep(0.0, 0.1, period1) - smoothstep(0.18, 0.4, period1),
            smoothstep(0.0, 0.1, period2) - smoothstep(0.18, 0.4, period2)
    ) * 0.6;

    lightning_frequency = clamp(lightning_frequency, 0.0, 1.0);
    vec3 lightning_color = vec3(1.000,0.380,0.380);

    float lightning_shape = noise(relative_pos.xy * 5. + mod(TIME, 15.11));

    return mix(color, lightning_color, lightning_frequency * lightning_shape);
}

vec3 darkBrambleColor(vec3 relative_pos)
{
    vec3 color = vec3(0.176,0.125,0.125);
    vec3 hole_color = vec3(1.000,0.953,0.722);

    float hole_position = smoothstep(0.05, 0.04, length(relative_pos - vec3(0.0,0.09,0.0)));
    return mix(color, hole_color, hole_position);
}

vec3 interloperColor() { return vec3(0.200,0.655,1.000); }

vec3 whiteHoleColor() { return vec3(1.0); }

vec3 colorize(Obj obj)
{
    vec3 col = vec3(0.0);

    switch(obj.color_index)
    {
        case SUN_COLOR_INDEX: col = sunColor(obj.relative_pos); break;

        case SUN_STATION_COLOR_INDEX: col = sunStationColor(); break;

        case EMBER_TWIN_COLOR_INDEX: col = emberTwinColor(); break;

        case ASH_TWIN_COLOR_INDEX: col = ashTwinColor(); break;

        case TIMBER_HEARTH_COLOR_INDEX: col = timberHearthColor(); break;

        case ATTLEROCK_COLOR_INDEX: col = attleRockColor(); break;

        case BRITTLE_HOLLOW_COLOR_INDEX: col = brittleHollowColor(obj.relative_pos); break;

        case HOLLOW_BLACK_HOLE_COLOR_INDEX: col = hollowBlackHoleColor(obj.relative_pos); break;

        case HOLLOWS_LANTERN_COLOR_INDEX: col = hollowLanternColor(); break;

        case GIANTS_DEEP_COLOR_INDEX: col = giantsDeepColor(obj.relative_pos); break;

        case DARK_BRAMBLE_COLOR_INDEX: col = darkBrambleColor(obj.relative_pos); break;

        case INTERLOPER_COLOR_INDEX: col = interloperColor(); break;

        case WHITE_HOLE_COLOR_INDEX: col = whiteHoleColor(); break;

        default: col = vec3(0.0); break;
    }

    return col;
}

vec3 background(vec2 uv)
{
    float wave = sin(uv.x * 55.0 + 50.0)
               * sin(uv.y * 48.0 + 37.)
               * cos((uv.y * uv.x) * 45.0 + 85.);

    vec3 black = vec3(0.0);
    vec3 white = vec3(1.0);

    return mix(black, white, smoothstep(0.99, 1.0, wave));
}

#define ZERO (min(iFrame,0))

vec3 calcNormal( in vec3 pos )
{
    // Simplified normal calculation for better performance
    const float h = 0.001;  // Larger epsilon for faster calculation
    vec2 k = vec2(1,-1);
    return normalize( k.xyy*scene( pos + k.xyy*h ).dist +
                      k.yyx*scene( pos + k.yyx*h ).dist +
                      k.yxy*scene( pos + k.yxy*h ).dist +
                      k.xxx*scene( pos + k.xxx*h ).dist );
}

void mainImage( out vec4 fragColor_out, in vec2 fragCoord )
{
    vec2 uv = (fragCoord * 2.0 - iResolution.xy) / min(iResolution.y, iResolution.x);
    vec2 m = vec2(cameraX, cameraY);  // Use uniform camera controls

    vec3 col = vec3(0.0, 0.0, 0.0);

    col = background(uv + m * 0.1) * backgroundStars + background(uv + m * 0.1 + 15.0) * backgroundStars;

    vec3 ray_origin = vec3(0.0, 0.0, -cameraDistance);

    vec2 start_xy = uv;
    vec3 ray_dir = normalize(vec3(start_xy, 1.5));

    ray_origin.yz *= rotation(-m.y);
    ray_dir.yz *= rotation(-m.y);

    ray_origin.xz *= rotation(-m.x);
    ray_dir.xz *= rotation(-m.x);

    float t = 0.0;
    vec3 ray_pos = ray_origin;
    Obj atmosphere_info = Obj(-1, 0.0, vec3(0.0));

    Obj object;

    // Heavily reduced iterations for Raspberry Pi (was 132)
    for (int i = 0; i < 16; i++)
    {
        ray_pos = ray_origin + ray_dir * t;

        object = scene(ray_pos);

        t += object.dist;

        if (object.dist < 0.015)
            atmosphere_info = object;

        if (t > 10.0 || object.dist < 0.001) break;
    }


    vec3 color = colorize(object);
    vec3 atmosphere_color = colorize(atmosphere_info);

    vec3 sun_light = vec3(1.000,0.686,0.141) * sunIntensity;
    float sun_ray = (0.015 * sunIntensity)/dot(uv,uv);

    if (t < 10.0)
    {
        col = color;

        // Simplified lighting - skip expensive normal calculation for most objects
        if (object.color_index != SUN_COLOR_INDEX
            && object.color_index != WHITE_HOLE_COLOR_INDEX
            && object.color_index != HOLLOWS_LANTERN_COLOR_INDEX)
        {
            // Simple fake lighting without normal calculation
            col *= 0.7 + 0.3 * clamp(dot(normalize(ray_pos), normalize(ray_dir)), 0.0, 1.0);
        }
    }
    else
    {
        col = mix(col, sun_light, sun_ray);
        if (atmosphere_info.color_index == GIANTS_DEEP_COLOR_INDEX)
            col = mix(col, atmosphere_color, 0.008/atmosphere_info.dist);

        if (atmosphere_info.color_index == TIMBER_HEARTH_COLOR_INDEX)
            col = mix(col, vec3(1.0), 0.004/atmosphere_info.dist);
    }


    // Second ray march for visual effects (VFX) - reduced for performance
    float vfx_t = 0.0;
    vec3 vfx_ray_pos = ray_origin;
    VFXObj obj;

    // Heavily reduced VFX iterations (was 40)
    for (int j = 0; j < 9; j++)
    {
        vfx_ray_pos = ray_origin + ray_dir * vfx_t;

        obj = VFX(vfx_ray_pos);

        float dist = obj.dist;

        vfx_t += dist;

        if (vfx_t > 10.0 || dist < 0.001) break;
    }
    if (vfx_t < 10.0 && vfx_t < t)
    {
        col = mix(col, obj.color, obj.opacity);
    }

    fragColor_out = vec4(col,1.0);
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
