#version 300 es
precision highp float;

// Blank Shader
// Original shader by lululombard

// Standard uniforms
uniform float iTime;
uniform vec2 iResolution;
uniform int frame;

// Configurable background color (default: black)
uniform vec3 backgroundColor;

// Input from vertex shader (unused but required)
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

void main() {
    fragColor = vec4(backgroundColor, 1.0);
}
