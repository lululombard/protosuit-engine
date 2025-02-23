use anyhow::{Context, Result};
use local_ip_address::local_ip;
use sdl2::{
    pixels::Color,
    rect::Rect,
    render::{Canvas, TextureCreator},
    ttf::Font,
    video::{Window, WindowContext},
};
use systemstat::{Platform, System};
use std::sync::Once;
use lazy_static::lazy_static;
use std::sync::Arc;
use hostname;

static TTF_INIT: Once = Once::new();

lazy_static! {
    static ref TTF_CONTEXT: Arc<sdl2::ttf::Sdl2TtfContext> = Arc::new(sdl2::ttf::init().unwrap());
}

pub struct DebugScene {
    canvas: Canvas<Window>,
    texture_creator: TextureCreator<WindowContext>,
    font: Font<'static, 'static>,
    system: System,
    mqtt_connected: bool,
    hostname: String,
}

impl DebugScene {
    pub fn new(canvas: Canvas<Window>) -> Result<Self> {
        let texture_creator = canvas.texture_creator();

        // Initialize TTF only once
        TTF_INIT.call_once(|| {
            sdl2::ttf::init().expect("Failed to initialize TTF");
        });

        let font_data = include_bytes!("../../assets/RobotoMono-Regular.ttf");
        let rwops = sdl2::rwops::RWops::from_bytes(font_data)
            .map_err(|e| anyhow::anyhow!("Failed to load font data: {}", e))?;

        // Use the static TTF context
        let font = TTF_CONTEXT.load_font_from_rwops(rwops, 24)
            .map_err(|e| anyhow::anyhow!("Failed to load font: {}", e))?;

        // Get hostname
        let hostname = hostname::get()
            .map(|h| h.to_string_lossy().to_string())
            .unwrap_or_else(|_| "unknown".to_string());

        Ok(Self {
            canvas,
            texture_creator,
            font,
            system: System::new(),
            mqtt_connected: false,
            hostname,
        })
    }

    pub fn set_mqtt_status(&mut self, connected: bool) {
        self.mqtt_connected = connected;
    }

    pub fn render(&mut self) -> Result<()> {
        self.canvas.set_draw_color(Color::RGB(0, 0, 0));
        self.canvas.clear();

        let (width, height) = self.canvas.output_size()
            .map_err(|e| anyhow::anyhow!("Failed to get canvas size: {}", e))?;
        let center_x = width as i32 / 2;
        let center_y = height as i32 / 2;

        // Get system information
        let ip = local_ip().context("Failed to get local IP")?;
        let uptime = self.system.uptime().context("Failed to get uptime")?;
        let mqtt_status = if self.mqtt_connected { "Connected" } else { "Disconnected" };

        // Render text lines
        let lines = vec![
            format!("Hostname: {}", self.hostname),
            format!("IP Address: {}", ip),
            format!("Uptime: {}h {}m {}s",
                uptime.as_secs() / 3600,
                (uptime.as_secs() % 3600) / 60,
                uptime.as_secs() % 60
            ),
            format!("MQTT Status: {}", mqtt_status),
        ];

        let line_height = 30;
        let total_height = lines.len() as i32 * line_height;
        let start_y = center_y - (total_height / 2);

        for (i, line) in lines.iter().enumerate() {
            let surface = self.font.render(line)
                .blended(Color::RGB(255, 255, 255))
                .map_err(|e| anyhow::anyhow!("Failed to render text: {}", e))?;

            let texture = self.texture_creator
                .create_texture_from_surface(&surface)
                .map_err(|e| anyhow::anyhow!("Failed to create texture: {}", e))?;

            let text_rect = Rect::new(
                center_x - (surface.width() as i32 / 2),
                start_y + (i as i32 * line_height),
                surface.width(),
                surface.height(),
            );

            self.canvas.copy(&texture, None, Some(text_rect))
                .map_err(|e| anyhow::anyhow!("Failed to copy texture: {}", e))?;
        }

        self.canvas.present();
        Ok(())
    }
}