use anyhow::{Context, Result};
use sdl2::video::Window;
use std::sync::Arc;
use dashmap::DashMap;
use std::process::{Child, Command};

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

    pub fn launch_app(&self, app_name: &str, command: &str, args: &[&str]) -> Result<()> {
        if self.running_apps.contains_key(app_name) {
            return Err(SDLError::AlreadyRunning(app_name.to_string()).into());
        }

        // Create SDL window for the application
        let video_subsystem = self.sdl_context.video()
            .map_err(|e| SDLError::SDLError(e.to_string()))?;

        let window = video_subsystem.window(app_name, self.window_width, self.window_height)
            .position_centered()
            .opengl()
            .build()
            .context("Failed to create window")?;

        // Launch the application process
        let mut child = Command::new(command)
            .args(args)
            .spawn()
            .context("Failed to spawn process")?;

        self.running_apps.insert(app_name.to_string(), (child, window));
        Ok(())
    }
}