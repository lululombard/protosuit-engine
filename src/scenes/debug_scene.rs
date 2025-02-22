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
use hostname;
use crate::modules::sdl_manager::TTF_CONTEXT;
use log;

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
        log::debug!("Creating new DebugScene");
        let texture_creator = canvas.texture_creator();

        log::debug!("Loading font for DebugScene");
        let font_data = include_bytes!("../../assets/RobotoMono-Regular.ttf");
        let rwops = sdl2::rwops::RWops::from_bytes(font_data)
            .map_err(|e| anyhow::anyhow!("Failed to load font data: {}", e))?;

        let font = TTF_CONTEXT.load_font_from_rwops(rwops, 24)
            .map_err(|e| anyhow::anyhow!("Failed to load font: {}", e))?;

        // Get hostname
        log::debug!("Getting hostname for DebugScene");
        let hostname = hostname::get()
            .map(|h| h.to_string_lossy().to_string())
            .unwrap_or_else(|_| "unknown".to_string());

        log::debug!("DebugScene created successfully");
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
        log::debug!("Setting MQTT status to: {}", connected);
        self.mqtt_connected = connected;
    }

    pub fn render(&mut self) -> Result<()> {
        log::trace!("Rendering DebugScene");
        self.canvas.set_draw_color(Color::RGB(0, 0, 0));
        self.canvas.clear();

        log::trace!("Getting canvas size");

        let (width, height) = self.canvas.output_size()
            .map_err(|e| anyhow::anyhow!("Failed to get canvas size: {}", e))?;
        let center_x = width as i32 / 2;
        let center_y = height as i32 / 2;

        log::trace!("Getting system information");

        // Get system information
        let ip = local_ip().context("Failed to get local IP")?;
        let uptime = self.system.uptime().context("Failed to get uptime")?;
        let mqtt_status = if self.mqtt_connected { "Connected" } else { "Disconnected" };

        log::trace!("Formatting text lines");

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

        log::trace!("Calculating line height and total height");

        let line_height = 30;
        let total_height = lines.len() as i32 * line_height;
        let start_y = center_y - (total_height / 2);

        log::trace!("Rendering text lines");

        for (i, line) in lines.iter().enumerate() {
            log::trace!("Rendering text line {}", i);
            log::trace!("Line: {}", line);

            log::trace!("Surfaceing text");
            let surface = self.font.render(line)
                .blended(Color::RGB(255, 255, 255))
                .map_err(|e| anyhow::anyhow!("Failed to render text: {}", e))?;

            log::trace!("Creating texture");
            let texture = self.texture_creator
                .create_texture_from_surface(&surface)
                .map_err(|e| anyhow::anyhow!("Failed to create texture: {}", e))?;

            log::trace!("Creating text rect");
            let text_rect = Rect::new(
                center_x - (surface.width() as i32 / 2),
                start_y + (i as i32 * line_height),
                surface.width(),
                surface.height(),
            );

            log::trace!("Copying texture to canvas");

            self.canvas.copy(&texture, None, Some(text_rect))
                .map_err(|e| anyhow::anyhow!("Failed to copy texture: {}", e))?;
        }

        log::trace!("Presenting canvas");

        self.canvas.present();
        Ok(())
    }
}