use anyhow::Result;
use sdl2::{
    pixels::Color,
    rect::Rect,
    render::{Canvas, TextureCreator},
    ttf::Font,
    video::{Window, WindowContext},
};
use chrono::Local;
use crate::modules::sdl_manager::TTF_CONTEXT;

pub struct IdleScene {
    canvas: Canvas<Window>,
    texture_creator: TextureCreator<WindowContext>,
    font: Font<'static, 'static>,
}

impl IdleScene {
    pub fn new(canvas: Canvas<Window>) -> Result<Self> {
        let texture_creator = canvas.texture_creator();

        let font_data = include_bytes!("../../assets/RobotoMono-Regular.ttf");
        let rwops = sdl2::rwops::RWops::from_bytes(font_data)
            .map_err(|e| anyhow::anyhow!("Failed to load font data: {}", e))?;

        let font = TTF_CONTEXT.load_font_from_rwops(rwops, 24)
            .map_err(|e| anyhow::anyhow!("Failed to load font: {}", e))?;

        Ok(Self {
            canvas,
            texture_creator,
            font,
        })
    }

    pub fn render(&mut self) -> Result<()> {
        self.canvas.set_draw_color(Color::RGB(0, 0, 0));
        self.canvas.clear();

        let (width, height) = self.canvas.output_size()
            .map_err(|e| anyhow::anyhow!("Failed to get canvas size: {}", e))?;
        let center_x = width as i32 / 2;
        let center_y = height as i32 / 2;

        // Get current date and time
        let now = Local::now();
        let date_time = now.format("%Y-%m-%d %H:%M:%S").to_string();

        // Render date and time
        let surface = self.font.render(&date_time)
            .blended(Color::RGB(255, 255, 255))
            .map_err(|e| anyhow::anyhow!("Failed to render text: {}", e))?;

        let texture = self.texture_creator
            .create_texture_from_surface(&surface)
            .map_err(|e| anyhow::anyhow!("Failed to create texture: {}", e))?;

        let text_rect = Rect::new(
            center_x - (surface.width() as i32 / 2),
            center_y - (surface.height() as i32 / 2),
            surface.width(),
            surface.height(),
        );

        self.canvas.copy(&texture, None, Some(text_rect))
            .map_err(|e| anyhow::anyhow!("Failed to copy texture: {}", e))?;

        self.canvas.present();
        Ok(())
    }
}