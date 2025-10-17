"""
Shader compilation utilities for OpenGL ES 3.0
Handles GLSL shader compilation and default uniform initialization
"""

import moderngl
import numpy as np


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
        import time

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
        }
    except Exception as e:
        print(f"Shader compilation error: {e}")
        return None
