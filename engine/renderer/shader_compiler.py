"""
OpenGL utilities for shader compilation and rendering
Handles GLSL shader compilation, blend shaders, and framebuffer management
"""

import moderngl
import numpy as np
import time


def compile_shader(
    ctx: moderngl.Context, shader_source: str, render_width: int, render_height: int
) -> dict:
    """
    Compile a GLSL fragment shader for rendering

    Note: Uniform default values are defined in config.yaml under each animation's
    'uniforms' section and are applied immediately after shader compilation.

    Args:
        ctx: ModernGL context
        shader_source: GLSL fragment shader source code
        render_width: Render target width in pixels
        render_height: Render target height in pixels

    Returns:
        Dict containing compiled shader program, VAO, and metadata:
        {
            'program': moderngl.Program,
            'vao': moderngl.VertexArray,
            'start_time': float,
            'frame': int,
            'source': str
        }
        Returns None if compilation fails
    """
    vertex_shader = f"""
    #version 300 es
    precision highp float;
    in vec2 in_position;
    out vec2 v_fragCoord;

    void main() {{
        gl_Position = vec4(in_position, 0.0, 1.0);
        v_fragCoord = (in_position + 1.0) * 0.5 * {float(render_width)};
    }}
    """

    try:
        try:
            program = ctx.program(
                vertex_shader=vertex_shader, fragment_shader=shader_source
            )
        except Exception as prog_error:
            print(f"Program creation failed: {prog_error}")
            print(f"Error type: {type(prog_error).__name__}")
            print(f"Vertex shader length: {len(vertex_shader)}")
            print(f"Fragment shader length: {len(shader_source)}")
            print(f"Fragment shader first 500 chars:\n{shader_source[:500]}")
            # Try to get more details from moderngl
            try:
                print(f"OpenGL version: {ctx.version_code}")
                print(f"Context info: {ctx.info}")
            except:
                pass
            raise

        # Create VAO with fullscreen quad
        vertices = np.array(
            [
                -1.0,
                -1.0,
                1.0,
                -1.0,
                -1.0,
                1.0,
                1.0,
                1.0,
            ],
            dtype="f4",
        )

        vbo = ctx.buffer(vertices.tobytes())
        vao = ctx.simple_vertex_array(program, vbo, "in_position")

        # Note: Custom uniform default values are defined in config.yaml
        # and are applied by display_manager._set_uniform_from_config()
        # immediately after shader compilation

        return {
            "program": program,
            "vao": vao,
            "start_time": time.time(),
            "frame": 0,
            "source": shader_source,  # Store source for recompilation
            "uses_audio_texture": "iChannel0" in program,
        }
    except Exception as e:
        print(f"Shader compilation error: {e}")
        return None


def create_blend_shader(ctx: moderngl.Context, fragment_source: str) -> tuple:
    """
    Create a shader program for blending two framebuffers during transitions.

    The fragment shader must define these uniforms:
        uniform sampler2D tex1;       // outgoing shader texture
        uniform sampler2D tex2;       // incoming shader texture
        uniform float alpha;          // transition progress (0.0 -> 1.0)
        uniform vec2 resolution;      // display dimensions
        uniform float iTime;          // current time (for animated transitions)
        uniform float blurEnabled;    // 1.0 if blur active (optional)
        uniform float blurStrengthMax; // max blur strength (optional)
    And receive:
        in vec2 uv;                   // normalized UV coordinates (0..1)

    Args:
        ctx: ModernGL context
        fragment_source: GLSL fragment shader source loaded from assets/shaders/transition/

    Returns:
        Tuple of (program, vao) for rendering blended output
    """
    vertex_shader = """
    #version 300 es
    precision highp float;
    in vec2 in_position;
    out vec2 uv;

    void main() {
        gl_Position = vec4(in_position, 0.0, 1.0);
        uv = (in_position + 1.0) * 0.5;
    }
    """

    program = ctx.program(vertex_shader=vertex_shader, fragment_shader=fragment_source)

    # Create fullscreen quad
    vertices = np.array(
        [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0],
        dtype="f4",
    )

    vbo = ctx.buffer(vertices.tobytes())
    vao = ctx.simple_vertex_array(program, vbo, "in_position")

    return program, vao


def create_framebuffers(ctx: moderngl.Context, width: int, height: int) -> list:
    """
    Create a pair of framebuffers for double-buffered rendering

    Args:
        ctx: ModernGL context
        width: Framebuffer width in pixels
        height: Framebuffer height in pixels

    Returns:
        List of two framebuffers [fbo1, fbo2]
    """
    tex1 = ctx.texture((width, height), 4)
    tex2 = ctx.texture((width, height), 4)

    fbo1 = ctx.framebuffer(color_attachments=[tex1])
    fbo2 = ctx.framebuffer(color_attachments=[tex2])

    return [fbo1, fbo2]
