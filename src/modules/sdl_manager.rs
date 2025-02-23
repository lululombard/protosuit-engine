use anyhow::{Context, Result};
use sdl2::video::Window;
use std::sync::Arc;
use dashmap::DashMap;
use std::process::{Child, Command};

pub struct SDLManager {
    sdl_context: Arc<sdl2::Sdl>,
    running_apps: DashMap<String, (Child, Window)>,
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

        // Hide cursor globally
        sdl_context.mouse().show_cursor(false);

        Ok(Self {
            sdl_context: Arc::new(sdl_context),
            running_apps: DashMap::new(),
        })
    }

    pub fn launch_app(&self, app_name: &str, command: &str, args: &[&str]) -> Result<Option<sdl2::render::Canvas<Window>>> {
        if self.running_apps.contains_key(app_name) {
            return Err(SDLError::AlreadyRunning(app_name.to_string()).into());
        }

        // Create SDL window for the application
        let video_subsystem = self.sdl_context.video()
            .map_err(|e| SDLError::SDLError(e.to_string()))?;

        let window = video_subsystem.window(app_name, 800, 600)
            .position_centered()
            .borderless()
            .opengl()
            .build()
            .context("Failed to create window")?;

        // For the idle/debug displays, we don't actually launch a process
        let child = if command == "true" {
            log::debug!("Creating display canvas for app: {}", app_name);
            let canvas = window.into_canvas()
                .present_vsync()
                .build()
                .context("Failed to create canvas")?;
            let window = canvas.window().clone();
            let child = Command::new("true").spawn().context("Failed to spawn dummy process")?;
            self.running_apps.insert(app_name.to_string(), (child, window));
            return Ok(Some(canvas));
        } else {
            Command::new(command)
                .args(args)
                .spawn()
                .context("Failed to spawn process")?
        };

        self.running_apps.insert(app_name.to_string(), (child, window));
        Ok(None)
    }

    pub fn stop_app(&self, app_name: &str) -> Result<()> {
        if let Some(mut entry) = self.running_apps.remove(app_name) {
            let (ref mut child, _) = entry.1;
            child.kill().context("Failed to kill process")?;
            child.wait().context("Failed to wait for process")?;
            Ok(())
        } else {
            Err(SDLError::NotFound(app_name.to_string()).into())
        }
    }

    pub fn get_window(&self, app_name: &str) -> Option<u32> {
        self.running_apps.get(app_name).map(|entry| {
            let window = &entry.value().1;
            window.raw() as u32
        })
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

    pub fn get_video_subsystem(&self) -> Result<sdl2::VideoSubsystem> {
        self.sdl_context.video()
            .map_err(|e| SDLError::SDLError(e.to_string()).into())
    }

    pub fn get_running_apps(&self) -> Vec<String> {
        self.running_apps.iter()
            .map(|entry| entry.key().clone())
            .collect()
    }
}

impl Drop for SDLManager {
    fn drop(&mut self) {
        let _ = self.cleanup();
    }
}
