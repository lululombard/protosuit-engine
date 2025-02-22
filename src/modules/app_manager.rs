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
    mqtt_status_rx: mpsc::Receiver<bool>,
    active_app: Option<String>,
    idle_display: Option<IdleDisplay>,
}

impl AppManager {
    pub fn new(mqtt_broker: &str, mqtt_port: u16) -> Result<Self> {
        let sdl_manager = Arc::new(SDLManager::new()?);
        let window_manager = Arc::new(WindowManager::new()?);

        let (command_tx, command_rx) = mpsc::channel(32);
        let (mqtt_status_tx, mqtt_status_rx) = mpsc::channel(32);

        let mqtt_handler = MQTTHandler::new(
            mqtt_broker,
            mqtt_port,
            &format!("protosuit-engine-client-{}", hostname::get()?.to_string_lossy()),
            command_tx,
            mqtt_status_tx,
        )?;

        // Create idle display window
        let (_, canvas) = (*sdl_manager).create_window_and_canvas("Protosuit Idle")?;
        let idle_display = IdleDisplay::new(canvas)?;

        Ok(Self {
            sdl_manager,
            window_manager,
            mqtt_handler: Some(mqtt_handler),
            command_rx,
            mqtt_status_rx,
            active_app: None,
            idle_display: Some(idle_display),
        })
    }

    pub async fn run(&mut self) -> Result<()> {
        let mut mqtt_handler = self.mqtt_handler.take()
            .context("MQTT handler not initialized")?;

        // Create shutdown channels
        let (mqtt_shutdown_tx, mqtt_shutdown_rx) = tokio::sync::oneshot::channel();

        // Replace the default shutdown receiver with our own
        mqtt_handler.shutdown_rx = mqtt_shutdown_rx;

        // Spawn MQTT handler task
        let mqtt_handle = tokio::spawn(async move {
            if let Err(e) = mqtt_handler.start().await {
                log::error!("MQTT handler error: {}", e);
            }
        });

        // Create an interval for updating the idle display
        let mut update_interval = interval(Duration::from_secs(1));

        // Handle Ctrl+C and SIGTERM
        let (shutdown_tx, mut shutdown_rx) = tokio::sync::oneshot::channel();

        tokio::spawn(async move {
            let mut sigterm = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
                .expect("Failed to create SIGTERM signal handler");

            tokio::select! {
                _ = tokio::signal::ctrl_c() => {
                    log::info!("Received Ctrl+C signal");
                }
                _ = sigterm.recv() => {
                    log::info!("Received SIGTERM signal");
                }
            }
            let _ = shutdown_tx.send(());
        });

        let result = loop {
            tokio::select! {
                Some(command) = self.command_rx.recv() => {
                    match command {
                        AppCommand::Start { name, command, args } => {
                            if let Err(e) = self.handle_start(&name, &command, &args).await {
                                break Err(e);
                            }
                        }
                        AppCommand::Stop { name } => {
                            if let Err(e) = self.handle_stop(&name).await {
                                break Err(e);
                            }
                        }
                        AppCommand::Switch { name } => {
                            if let Err(e) = self.handle_switch(&name).await {
                                break Err(e);
                            }
                        }
                    }
                }
                Some(mqtt_connected) = self.mqtt_status_rx.recv() => {
                    if let Some(idle_display) = &mut self.idle_display {
                        idle_display.set_mqtt_status(mqtt_connected);
                    }
                }
                _ = update_interval.tick() => {
                    if self.active_app.is_none() {
                        if let Some(idle_display) = &mut self.idle_display {
                            if let Err(e) = idle_display.render() {
                                break Err(e);
                            }
                        }
                    }
                }
                _ = &mut shutdown_rx => {
                    log::info!("Shutdown signal received, cleaning up...");
                    // Send shutdown signal to MQTT handler
                    let _ = mqtt_shutdown_tx.send(());
                    // Wait for MQTT handler to finish
                    let _ = mqtt_handle.await;
                    // Stop all running apps
                    if let Err(e) = self.cleanup().await {
                        break Err(e);
                    }
                    break Ok(());
                }
            }
        };

        log::info!("App manager shutting down");
        result
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

    async fn cleanup(&mut self) -> Result<()> {
        // Stop all running apps
        let running_apps: Vec<String> = self.sdl_manager.get_running_apps();
        for app_name in running_apps {
            if let Err(e) = self.handle_stop(&app_name).await {
                log::error!("Failed to stop {}: {}", app_name, e);
            }
        }
        Ok(())
    }
}
