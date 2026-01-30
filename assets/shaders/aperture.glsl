#version 300 es
precision highp float;

// Aperture Shader
// Original shader by lululombard

// Standard uniforms
uniform float iTime;
uniform vec2 iResolution;

// MQTT-controllable uniforms
uniform float rotationSpeed;    // Rotation speed (positive = CW, negative = CCW, 0 = static)
uniform float focusSharpness;   // Edge sharpness (higher = sharper, default: 360.0)
uniform vec3 apertureColor;     // Aperture color (default: orange)

// Input from vertex shader
in vec2 v_fragCoord;

// Output
out vec4 fragColor;

const float PI = 3.141592;

// SDF functions
float ring(in vec2 p)
{
   float outerSize = 0.7;
   float innerSize = 0.416;
   float len = length(p);
   return max(len - outerSize, innerSize - len);
}

float box( in vec2 p, in vec2 b )
{
    vec2 d = abs(p)-b;
    return length(max(d,0.0)) + min(max(d.x,d.y),0.0);
}

mat2 rotate2d(float _angle){
    return mat2(cos(_angle),-sin(_angle),
                sin(_angle),cos(_angle));
}

float applyBoxes( in vec2 p )
{
    float result = 1.0;
    // Static aperture blades
    p = rotate2d(PI / 64.0) * p;
    for (int i = 0; i < 8; i += 1)
    {
        mat2 angle = rotate2d(float(i) * 2.0 * PI / 8.0);
        vec2 offset = vec2(0.380,0.42);
        result = min(result, box((angle * (p)) + offset, vec2(0.045,0.590)));
    }
    return result;
}

float focus(float sdf, float sharpness)
{
    return (sdf + (1.0 / (sharpness * 2.0))) * sharpness;
}

void mainImage( out vec4 fragColor_out, in vec2 fragCoord ) {
   vec2 uv = fragCoord.xy / iResolution.yy;
   float ratio = iResolution.x / iResolution.y;

    // Output to screen
   uv -= vec2(0.5 * ratio, 0.5);
   uv *= 1.5;  // Lower value = bigger aperture

   // Rotate the entire aperture around center
   // rotationSpeed: positive = CW, negative = CCW, 0 = static
   uv = rotate2d(iTime * rotationSpeed) * uv;

   // Apply focus with controllable sharpness
   float col = clamp(1.0 - focus(ring(uv), focusSharpness), 0.0, 1.0);
   col = min(col, clamp(focus(applyBoxes(uv), focusSharpness), 0.0, 1.0));

   // Apply color
   vec3 finalColor = apertureColor * col;

   fragColor_out = vec4(finalColor, 1.0);
}

void main() {
    mainImage(fragColor, v_fragCoord);
}
