#version 300 es
precision highp float;

// Echo Signal Shader
// Original source from Shadertoy (author unknown)
// If you know the original author, please open an issue to properly credit them

// Standard uniforms
uniform float iTime;
uniform vec2 iResolution;

// MQTT-controllable uniforms
uniform float speed;            // Animation speed (default: 1.0)
uniform float radius;           // Base radius (default: 0.5)
uniform float width;            // Circle width/sharpness (default: 0.8)
uniform float power;            // Intensity/brightness (default: 0.1)
uniform float colorHue;         // Hue offset (default: 0.5)
uniform float colorSaturation;  // Color saturation (default: 1.0)

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

vec3 drawCircle(vec2 pos, float rad, float wid, float pwr, vec4 color)
{
    float dist1 = length(pos);
    dist1 = fract((dist1 * 5.0) - fract(iTime * speed));
    float dist2 = dist1 - rad;
    float intensity = pow(rad / abs(dist2), wid);
    vec3 col = color.rgb * intensity * pwr * max((0.8- abs(dist2)), 0.0);
    return col;
}

vec3 hsv2rgb(float h, float s, float v)
{
    vec4 t = vec4(1.0, 2.0/3.0, 1.0/3.0, 3.0);
    vec3 p = abs(fract(vec3(h) + t.xyz) * 6.0 - vec3(t.w));
    return v * mix(vec3(t.x), clamp(p - vec3(t.x), 0.0, 1.0), s);
}

void mainImage( out vec4 fragColor_out, in vec2 fragCoord )
{
    // -1.0 ~ 1.0
    vec2 pos = (fragCoord.xy * 2.0 - iResolution.xy) / min(iResolution.x, iResolution.y);

    float h = mix(colorHue, colorHue + 0.15, length(pos));
    vec4 color = vec4(hsv2rgb(h, colorSaturation, 1.0), 1.0);
    vec3 finalColor = drawCircle(pos, radius, width, power, color);

    fragColor_out = vec4(finalColor, 1.0);
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
