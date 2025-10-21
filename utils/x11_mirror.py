#!/usr/bin/env python3
"""
X11 Screen Mirror - Hardware accelerated with OpenGL
Uses pygame + moderngl for GPU-based screen mirroring with minimal CPU overhead
"""

import os
import sys

def mirror_screen_gl(source_x, source_y, width, height, target_x, target_y):
    """
    Mirror screen region using OpenGL hardware acceleration
    """
    print(f"[x11-mirror] Starting hardware-accelerated mirror")
    print(f"[x11-mirror] Source: {source_x},{source_y} {width}x{height}")
    print(f"[x11-mirror] Target: {target_x},{target_y}")

    try:
        import pygame
        import moderngl
        import mss

        # Set window position
        os.environ['SDL_VIDEO_WINDOW_POS'] = f"{target_x},{target_y}"

        # Initialize pygame with OpenGL
        pygame.init()
        pygame.display.set_mode((width, height), pygame.OPENGL | pygame.DOUBLEBUF | pygame.NOFRAME)
        pygame.display.set_caption("Mirror")

        # Create ModernGL context (require OpenGL 3.1 for Raspberry Pi)
        ctx = moderngl.create_context(require=310)

        # Create texture for screen capture
        texture = ctx.texture((width, height), 3)
        texture.filter = (moderngl.NEAREST, moderngl.NEAREST)

        # Create "MIRRORED" text overlay
        pygame.font.init()
        font = pygame.font.SysFont('monospace', 24, bold=True)
        text_yellow = font.render('MIRRORED', True, (255, 255, 0))
        text_black = font.render('MIRRORED', True, (0, 0, 0))

        # Create a surface for the text with alpha channel
        text_width, text_height = text_yellow.get_size()
        text_surface = pygame.Surface((text_width + 2, text_height + 2), pygame.SRCALPHA)
        text_surface.fill((0, 0, 0, 0))  # Transparent background

        # Draw black outline
        for dx, dy in [(-1,-1), (-1,0), (-1,1), (0,-1), (0,1), (1,-1), (1,0), (1,1)]:
            text_surface.blit(text_black, (1 + dx, 1 + dy))
        # Draw yellow text on top
        text_surface.blit(text_yellow, (1, 1))

        # Convert text surface to RGBA and create OpenGL texture
        # Use flipped=False to avoid upside-down text
        text_data = pygame.image.tostring(text_surface, 'RGBA', False)
        text_texture = ctx.texture((text_width + 2, text_height + 2), 4, text_data)
        text_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)

        # Calculate text position (centered at top)
        text_x = (width - text_width - 2) / 2
        text_y = 10

        # Create fullscreen quad for screen capture
        import struct
        vertices = ctx.buffer(struct.pack('16f',
            # position (x, y), texcoord (u, v)
            -1.0, -1.0,  0.0, 1.0,  # bottom-left
             1.0, -1.0,  1.0, 1.0,  # bottom-right
            -1.0,  1.0,  0.0, 0.0,  # top-left
             1.0,  1.0,  1.0, 0.0,  # top-right
        ))

        # Simple shader to display texture (OpenGL 3.1 compatible)
        prog = ctx.program(
            vertex_shader='''
                #version 140
                in vec2 in_vert;
                in vec2 in_texcoord;
                out vec2 v_texcoord;
                void main() {
                    v_texcoord = in_texcoord;
                    gl_Position = vec4(in_vert, 0.0, 1.0);
                }
            ''',
            fragment_shader='''
                #version 140
                uniform sampler2D texture0;
                in vec2 v_texcoord;
                out vec4 fragColor;
                void main() {
                    fragColor = texture(texture0, v_texcoord);
                }
            ''',
        )

        vao = ctx.vertex_array(prog, [(vertices, '2f 2f', 'in_vert', 'in_texcoord')])

        # Create shader for text overlay with alpha blending
        prog_text = ctx.program(
            vertex_shader='''
                #version 140
                in vec2 in_vert;
                in vec2 in_texcoord;
                out vec2 v_texcoord;
                void main() {
                    v_texcoord = in_texcoord;
                    gl_Position = vec4(in_vert, 0.0, 1.0);
                }
            ''',
            fragment_shader='''
                #version 140
                uniform sampler2D texture0;
                in vec2 v_texcoord;
                out vec4 fragColor;
                void main() {
                    fragColor = texture(texture0, v_texcoord);
                }
            ''',
        )

        # Create quad for text overlay (positioned at top center)
        tx1 = (text_x / width) * 2.0 - 1.0
        tx2 = ((text_x + text_width + 2) / width) * 2.0 - 1.0
        ty1 = 1.0 - ((text_y + text_height + 2) / height) * 2.0
        ty2 = 1.0 - (text_y / height) * 2.0

        text_vertices = ctx.buffer(struct.pack('16f',
            tx1, ty1,  0.0, 1.0,  # bottom-left
            tx2, ty1,  1.0, 1.0,  # bottom-right
            tx1, ty2,  0.0, 0.0,  # top-left
            tx2, ty2,  1.0, 0.0,  # top-right
        ))

        text_vao = ctx.vertex_array(prog_text, [(text_vertices, '2f 2f', 'in_vert', 'in_texcoord')])

        # Enable alpha blending for text
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA

        # Set up screen capture
        sct = mss.mss()
        monitor = {
            "top": source_y,
            "left": source_x,
            "width": width,
            "height": height
        }

        print("[x11-mirror] OpenGL context initialized")

        clock = pygame.time.Clock()
        running = True

        while running:
            # Handle events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_q, pygame.K_ESCAPE):
                        running = False

            # Capture screen
            img = sct.grab(monitor)

            # Upload to GPU texture (this is the only CPU->GPU transfer)
            texture.write(img.rgb)

            # Render with OpenGL
            ctx.clear(0.0, 0.0, 0.0)

            # Draw screen capture
            texture.use(0)
            vao.render(moderngl.TRIANGLE_STRIP)

            # Draw text overlay with alpha blending
            text_texture.use(0)
            text_vao.render(moderngl.TRIANGLE_STRIP)

            pygame.display.flip()
            clock.tick(60)

        sct.close()
        pygame.quit()

        return True

    except ImportError as e:
        print(f"[x11-mirror] ERROR: Missing dependency: {e}")
        print("[x11-mirror] OpenGL mirror requires: moderngl, moderngl-window, mss")
        return False
    except Exception as e:
        print(f"[x11-mirror] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if len(sys.argv) != 7:
        print("Usage: x11-mirror.py <src_x> <src_y> <width> <height> <target_x> <target_y>")
        sys.exit(1)

    source_x = int(sys.argv[1])
    source_y = int(sys.argv[2])
    width = int(sys.argv[3])
    height = int(sys.argv[4])
    target_x = int(sys.argv[5])
    target_y = int(sys.argv[6])

    success = mirror_screen_gl(source_x, source_y, width, height, target_x, target_y)
    sys.exit(0 if success else 1)
