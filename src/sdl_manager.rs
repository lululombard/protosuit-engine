use anyhow::{Context, Result};
use sdl2::video::{Window, WindowPos};
use std::sync::Arc;
use dashmap::DashMap;
use std::process::{Child, Command};
use log;

const DEFAULT_WINDOW_WIDTH: u32 = 720;
const DEFAULT_WINDOW_HEIGHT: u32 = 720;

#[derive(Debug, Clone, Copy)]
pub enum DisplayRotation {
    Normal,
    Right,
    Left,
    Flipped,
}

impl DisplayRotation {
    fn from_env() -> Self {
        let rotation = match std::env::var("SDL_DISPLAY_ROTATION").as_deref() {
            Ok("right") => DisplayRotation::Right,
            Ok("left") => DisplayRotation::Left,
            Ok("flipped") => DisplayRotation::Flipped,
            Ok(value) => {
                log::debug!("Unknown rotation value '{}', defaulting to normal", value);
                DisplayRotation::Normal
            }
            Err(_) => {
                log::debug!("No SDL_DISPLAY_ROTATION set, defaulting to normal");
                DisplayRotation::Normal
            }
        };
        log::info!("Using display rotation: {:?}", rotation);
        rotation
    }

    fn to_degrees(&self) -> f64 {
        match self {
            DisplayRotation::Normal => 0.0,
            DisplayRotation::Right => 90.0,
            DisplayRotation::Left => 270.0,
            DisplayRotation::Flipped => 180.0,
        }
    }
}

pub struct SDLManager {
    sdl_context: Arc<sdl2::Sdl>,
    running_apps: DashMap<String, (Child, Window)>,
    window_width: u32,
    window_height: u32,
    rotation: DisplayRotation,
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

        // Get rotation from environment
        let rotation = DisplayRotation::from_env();

        Ok(Self {
            sdl_context: Arc::new(sdl_context),
            running_apps: DashMap::new(),
            window_width,
            window_height,
            rotation,
        })
    }

    pub fn launch_app(&self, app_name: &str, command: &str, args: &[&str]) -> Result<()> {
        if self.running_apps.contains_key(app_name) {
            return Err(SDLError::AlreadyRunning(app_name.to_string()).into());
        }

        // Create SDL window for the application
        let video_subsystem = self.sdl_context.video()
            .map_err(|e| SDLError::SDLError(e.to_string()))?;

        // Adjust dimensions based on rotation
        let (width, height) = match self.rotation {
            DisplayRotation::Right | DisplayRotation::Left => (self.window_height, self.window_width),
            _ => (self.window_width, self.window_height),
        };

        let window = video_subsystem.window(app_name, width, height)
            .position(WindowPos::Centered)
            .opengl()
            .build()
            .context("Failed to create window")?;

        // Create a canvas to handle rotation
        let mut canvas = window.into_canvas()
            .present_vsync()
            .build()
            .context("Failed to create canvas")?;

        // Set rotation
        canvas.set_logical_size(self.window_width, self.window_height)
            .map_err(|e| SDLError::SDLError(e.to_string()))?;

        // Apply rotation
        let rotation_degrees = self.rotation.to_degrees();
        log::debug!("Setting canvas rotation to {} degrees", rotation_degrees);
        canvas.set_draw_color(sdl2::pixels::Color::RGB(0, 0, 0));
        canvas.clear();
        canvas.present();

        let window = canvas.into_window();

        // For the idle display, we don't actually launch a process
        let child = if command == "true" {
            Command::new("true").spawn().context("Failed to spawn dummy process")?
        } else {
            Command::new(command)
                .args(args)
                .spawn()
                .context("Failed to spawn process")?
        };

        self.running_apps.insert(app_name.to_string(), (child, window));
        Ok(())
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
}