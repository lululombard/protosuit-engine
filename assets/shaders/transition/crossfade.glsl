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

vec4 blur(sampler2D tex, vec2 uv, float strength) {
    if (strength <= 0.0) {
        return texture(tex, uv);
    }

    vec2 texelSize = 1.0 / resolution;
    vec4 result = vec4(0.0);
    float total = 0.0;

    float kernel[9];
    kernel[0] = 1.0; kernel[1] = 2.0; kernel[2] = 1.0;
    kernel[3] = 2.0; kernel[4] = 4.0; kernel[5] = 2.0;
    kernel[6] = 1.0; kernel[7] = 2.0; kernel[8] = 1.0;

    int index = 0;
    for (int y = -1; y <= 1; y++) {
        for (int x = -1; x <= 1; x++) {
            vec2 offset = vec2(float(x), float(y)) * texelSize * strength;
            result += texture(tex, uv + offset) * kernel[index];
            total += kernel[index];
            index++;
        }
    }

    return result / total;
}

void main() {
    float t = alpha * alpha * (3.0 - 2.0 * alpha);
    float blurStrength = blurEnabled * 4.0 * alpha * (1.0 - alpha) * blurStrengthMax;

    vec4 col1 = blur(tex1, uv, blurStrength);
    vec4 col2 = blur(tex2, uv, blurStrength);

    fragColor = mix(col1, col2, t);
}
