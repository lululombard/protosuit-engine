use anyhow::{Context, Result};
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio::time::{interval, Duration};
use hostname;
use crate::modules::{
    mqtt_handler::{AppCommand, MQTTHandler},
    sdl_manager::SDLManager,
    window_manager::WindowManager,
    idle_display::IdleDisplay,
};

pub struct AppManager {
    sdl_manager: Arc<SDLManager>,
    window_manager: Arc<WindowManager>,
    mqtt_handler: Option<MQTTHandler>,
    command_rx: mpsc::Receiver<AppCommand>,
    active_app: Option<String>,
    idle_display: Option<IdleDisplay>,
}

impl AppManager {
    pub fn new(mqtt_broker: &str, mqtt_port: u16) -> Result<Self> {
        let sdl_manager = Arc::new(SDLManager::new()?);
        let window_manager = Arc::new(WindowManager::new()?);

        let (command_tx, command_rx) = mpsc::channel(32);
        let mqtt_handler = MQTTHandler::new(
            mqtt_broker,
            mqtt_port,
            &format!("protosuit-engine-client-{}", hostname::get()?.to_string_lossy()),
            command_tx,
        )?;

        // Create idle display window
        let video_subsystem = sdl_manager.get_video_subsystem()?;
        let window = video_subsystem.window("Protosuit Idle", 720, 720)
            .position_centered()
            .borderless()
            .opengl()
            .build()
            .context("Failed to create idle window")?;

        let idle_display = IdleDisplay::new(window)?;

        Ok(Self {
            sdl_manager,
            window_manager,
            mqtt_handler: Some(mqtt_handler),
            command_rx,
            active_app: None,
            idle_display: Some(idle_display),
        })
    }

    pub async fn run(&mut self) -> Result<()> {
        let mut mqtt_handler = self.mqtt_handler.take()
            .context("MQTT handler not initialized")?;

        // Spawn MQTT handler task
        let _mqtt_handle = tokio::spawn(async move {
            if let Err(e) = mqtt_handler.start().await {
                log::error!("MQTT handler error: {}", e);
            }
        });

        // Create an interval for updating the idle display
        let mut update_interval = interval(Duration::from_secs(1));

        loop {
            tokio::select! {
                Some(command) = self.command_rx.recv() => {
                    match command {
                        AppCommand::Start { name, command, args } => {
                            self.handle_start(&name, &command, &args).await?;
                        }
                        AppCommand::Stop { name } => {
                            self.handle_stop(&name).await?;
                        }
                        AppCommand::Switch { name } => {
                            self.handle_switch(&name).await?;
                        }
                    }
                }
                _ = update_interval.tick() => {
                    if self.active_app.is_none() {
                        if let Some(idle_display) = &mut self.idle_display {
                            idle_display.render()?;
                        }
                    }
                }
            }
        }
    }

    async fn handle_start(&mut self, name: &str, command: &str, args: &[String]) -> Result<()> {
        // Convert args to &str slice
        let args_str: Vec<&str> = args.iter().map(AsRef::as_ref).collect();

        // Launch the application
        self.sdl_manager.launch_app(name, command, &args_str)?;

        // If this is the first app, make it active
        if self.active_app.is_none() {
            self.active_app = Some(name.to_string());
            if let Some(window_id) = self.sdl_manager.get_window(name) {
                self.window_manager.focus_window(window_id)?;
            }
        } else {
            // Minimize the new window if it's not the active app
            if let Some(window_id) = self.sdl_manager.get_window(name) {
                self.window_manager.minimize_window(window_id)?;
            }
        }

        Ok(())
    }

    async fn handle_stop(&mut self, name: &str) -> Result<()> {
        // Stop the application
        self.sdl_manager.stop_app(name)?;

        // If this was the active app, clear the active app state
        if self.active_app.as_deref() == Some(name) {
            self.active_app = None;
        }

        Ok(())
    }

    async fn handle_switch(&mut self, name: &str) -> Result<()> {
        // If the app exists and it's not already active
        if let Some(window_id) = self.sdl_manager.get_window(name) {
            // Minimize the currently active app if it exists
            if let Some(active_name) = &self.active_app {
                if let Some(active_window_id) = self.sdl_manager.get_window(active_name) {
                    self.window_manager.minimize_window(active_window_id)?;
                }
            }

            // Focus the new app
            self.window_manager.focus_window(window_id)?;
            self.active_app = Some(name.to_string());
        }

        Ok(())
    }
}
