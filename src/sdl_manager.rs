use anyhow::{Context, Result};
use sdl2::video::{Window, WindowPos};
use std::sync::Arc;
use dashmap::DashMap;
use std::process::{Child, Command};
use log;

const DEFAULT_WINDOW_WIDTH: u32 = 720;
const DEFAULT_WINDOW_HEIGHT: u32 = 720;

pub struct SDLManager {
    sdl_context: Arc<sdl2::Sdl>,
    running_apps: DashMap<String, (Child, Window)>,
    window_width: u32,
    window_height: u32,
}

#[derive(Debug, thiserror::Error)]
pub enum SDLError {
    #[error("Application {0} is already running")]
    AlreadyRunning(String),
    #[error("Application {0} not found")]
    NotFound(String),
    #[error("SDL error: {0}")]
    SDLError(String),
}

impl SDLManager {
    pub fn new() -> Result<Self> {
        // Set SDL hint to respect existing display settings
        sdl2::hint::set("SDL_VIDEO_ALLOW_SCREENSAVER", "1");
        sdl2::hint::set("SDL_VIDEO_X11_XRANDR", "1");
        sdl2::hint::set("SDL_VIDEO_X11_XVIDMODE", "1");

        let sdl_context = sdl2::init()
            .map_err(|e| SDLError::SDLError(e.to_string()))
            .context("Failed to initialize SDL")?;

        // Get window dimensions from environment variables or use defaults
        let window_width = std::env::var("SDL_WINDOW_WIDTH")
            .ok()
            .and_then(|w| w.parse().ok())
            .unwrap_or(DEFAULT_WINDOW_WIDTH);

        let window_height = std::env::var("SDL_WINDOW_HEIGHT")
            .ok()
            .and_then(|h| h.parse().ok())
            .unwrap_or(DEFAULT_WINDOW_HEIGHT);

        Ok(Self {
            sdl_context: Arc::new(sdl_context),
            running_apps: DashMap::new(),
            window_width,
            window_height,
        })
    }

    pub fn create_window_and_canvas(&self, title: &str) -> Result<(Window, sdl2::render::Canvas<Window>)> {
        let video_subsystem = self.sdl_context.video()
            .map_err(|e| SDLError::SDLError(e.to_string()))?;

        let window = video_subsystem.window(title, 800, 600)
            .position_centered()
            .borderless()
            .opengl()
            .build()
            .context("Failed to create window")?;

        let canvas = window.into_canvas()
            .present_vsync()
            .build()
            .context("Failed to create canvas")?;

        let window = canvas.window().clone();
        Ok((window, canvas))
    }

    pub fn launch_app(&self, app_name: &str, command: &str, args: &[&str]) -> Result<Option<sdl2::render::Canvas<Window>>> {
        if self.running_apps.contains_key(app_name) {
            return Err(SDLError::AlreadyRunning(app_name.to_string()).into());
        }

        let video_subsystem = self.sdl_context.video()
            .map_err(|e| SDLError::SDLError(e.to_string()))?;

        let window = video_subsystem.window(app_name, width, height)
            .position(WindowPos::Centered)
            .opengl()
            .borderless()
            .build()
            .context("Failed to create window")?;

        let mut canvas = window.into_canvas()
            .present_vsync()
            .build()
            .context("Failed to create canvas")?;

        // Set canvas size
        canvas.set_logical_size(self.window_width, self.window_height)
            .map_err(|e| SDLError::SDLError(e.to_string()))?;

        canvas.set_draw_color(sdl2::pixels::Color::RGB(0, 0, 0));
        canvas.clear();
        canvas.present();

        let window = canvas.window().clone();

        log::debug!("Launching app: {} with command: {}", app_name, command);

        // For the idle display, we don't actually launch a process
        let child = if command == "true" {
            log::debug!("Creating idle display canvas for app: {}", app_name);
            Command::new("true").spawn().context("Failed to spawn dummy process")?
        } else {
            Command::new(command)
                .args(args)
                .spawn()
                .context("Failed to spawn process")?
        };

        self.running_apps.insert(app_name.to_string(), (child, window));

        if command == "true" {
            log::debug!("Returning canvas for idle display app: {}", app_name);
            Ok(Some(canvas))
        } else {
            Ok(None)
        }
    }

    pub fn get_window(&self, app_name: &str) -> Option<u32> {
        self.running_apps.get(app_name).map(|entry| {
            let window = &entry.value().1;
            window.raw() as u32
        })
    }

    pub fn get_window_obj(&self, app_name: &str) -> Result<Window> {
        if let Some(entry) = self.running_apps.get(app_name) {
            let (_, window) = entry.value();
            Ok(window.clone())
        } else {
            Err(SDLError::NotFound(app_name.to_string()).into())
        }
    }

    pub fn cleanup(&self) -> Result<()> {
        for mut entry in self.running_apps.iter_mut() {
            let (ref mut child, _) = entry.value_mut();
            child.kill().context("Failed to kill process")?;
            child.wait().context("Failed to wait for process")?;
        }
        self.running_apps.clear();
        Ok(())
    }

    pub fn store_window(&self, app_name: &str, window: Window) -> Result<()> {
        // Use a dummy process that exits immediately
        let child = Command::new("true")
            .spawn()
            .context("Failed to spawn dummy process")?;

        self.running_apps.insert(app_name.to_string(), (child, window));
        Ok(())
    }
}