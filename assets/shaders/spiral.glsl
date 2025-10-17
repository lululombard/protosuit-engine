#version 300 es
precision highp float;

// Converted to moderngl format for protosuit-engine

// Uniforms from moderngl
uniform float iTime;
uniform vec2 iResolution;

// Custom uniforms for interactive control
uniform vec3 spiralColor;      // RGB color of the spiral (0.0-1.0)
uniform float spiralSpeed;     // Speed multiplier (0.1-5.0)
uniform float spiralDirection; // Direction: -1.0 = clockwise, 1.0 = counter-clockwise
uniform float spiralSize;      // Size/scale of the spiral (10.0-100.0)
uniform float spiralIntensity; // Overall brightness/intensity (0.1-2.0)
uniform float spiralFade;      // Fade effect strength (0.0-2.0)

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

// Comparison functions
float gt(float v1, float v2)
{
    return step(v2,v1);
}

float lt(float v1, float v2)
{
    return step(v1, v2);
}

float between(float val, float start, float end)
{
    return gt(val,start)*lt(val,end);
}

float eq(float v1, float v2, float e)
{
    return between(v1, v2-e, v2+e);
}

float s_gt(float v1, float v2, float e)
{
    return smoothstep(v2-e, v2+e, v1);
}

float s_lt(float v1, float v2, float e)
{
    return smoothstep(v1-e, v1+e, v2);
}

float s_between(float val, float start, float end, float epsilon)
{
    return s_gt(val,start,epsilon)*s_lt(val,end,epsilon);
}

float s_eq(float v1, float v2, float e, float s_e)
{
    return s_between(v1, v2-e, v2+e, s_e);
}

void mainImage( out vec4 fragColor_out, in vec2 fragCoord )
{
    vec2 uv = fragCoord/iResolution.xy;
    float ratio = iResolution.y/iResolution.x;

    float viewPortCenter = 0.5;

    vec2 xy = uv - vec2(viewPortCenter);
    xy = vec2(xy.x, xy.y*ratio);

    xy *= spiralSize;  // Use uniform for spiral size

    float x = xy.x;
    float y = xy.y;

    float r = sqrt(x*x + y*y);
    float a = atan(y,x);

    // Apply direction and speed to time
    float time = iTime * spiralSpeed * spiralDirection;

    vec4 col = vec4(0);

    // Create spiral pattern with customizable parameters
    float spiral1 = s_eq(cos(r-a+time), sin(a-r/2.+time*2.), 0.5, 0.2);
    float spiral2 = s_eq(cos(r-a+time), sin(a-r/2.+time*2.), 0.5, 0.2);

    // Apply color
    col.rgb = spiralColor * (spiral1 + spiral2) * spiralIntensity;
    col.a = spiral1 + spiral2;

    // Apply fade effects
    float distance = length(xy);
    col.rgba *= distance/3.0;  // Inner fade
    col.rgba *= 1.0 - (distance/10.0) * spiralFade;  // Outer fade

    fragColor_out = col;
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
