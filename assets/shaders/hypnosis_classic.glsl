#version 300 es
precision highp float;

// Hypnosis Classic Shader

// Standard uniforms
uniform float iTime;
uniform vec2 iResolution;

// MQTT-controllable uniforms
uniform float speed;          // Rotation speed (default: 2.0)
uniform float spiralScale;    // Spiral tightness (default: 20.0)
uniform vec3 foregroundColor; // Pattern color (default: magenta)
uniform vec3 backgroundColor; // Background color (default: black)

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

void mainImage( out vec4 fragColor_out, in vec2 fragCoord )
{
	vec2 uv = (fragCoord - 0.5 * iResolution.xy) / iResolution.y;
    vec2 st = vec2(atan(uv.x, uv.y), length(uv));
    uv = vec2(st.x / 6.2831 + iTime * speed - st.y * spiralScale, st.y);
    float smf = 1.5*fwidth(uv.x);
    float m = fract(uv.x);
    float mask = smoothstep(0., smf, abs(m-.5)-.25);
    vec3 col = mix(backgroundColor, foregroundColor, mask);
    fragColor_out = vec4(col, 1.0);
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
