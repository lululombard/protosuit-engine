use anyhow::{Context, Result};
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio::time::{interval, Duration};
use hostname;
use crate::modules::{
    mqtt_handler::{AppCommand, MQTTHandler},
    sdl_manager::SDLManager,
    window_manager::WindowManager,
};
use crate::scenes::{
    debug_scene::DebugScene,
    idle_scene::IdleScene,
};

pub struct AppManager {
    sdl_manager: Arc<SDLManager>,
    window_manager: Arc<WindowManager>,
    mqtt_handler: Option<MQTTHandler>,
    command_rx: mpsc::Receiver<AppCommand>,
    mqtt_status_rx: mpsc::Receiver<bool>,
    active_scene: String, // Track which scene is currently active
    debug_scene: Option<DebugScene>,
    idle_scene: Option<IdleScene>,
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

        // Get default scene from environment variable, fallback to "debug"
        let mut default_scene = std::env::var("PROTOSUIT_ENGINE_DEFAULT_SCENE")
            .unwrap_or_else(|_| {
                log::info!("PROTOSUIT_ENGINE_DEFAULT_SCENE not set, defaulting to 'debug'");
                "debug".to_string()
            });

        // Validate the scene name
        if !matches!(default_scene.as_str(), "debug" | "idle") {
            log::warn!("Unknown default scene '{}', falling back to debug", default_scene);
            default_scene = "debug".to_string();
        }

        log::info!("Loading default scene: {}", default_scene);

        // Initialize scenes as None
        let mut debug_scene = None;
        let mut idle_scene = None;

        // Create the default scene
        match default_scene.as_str() {
            "debug" => {
                log::debug!("Creating debug scene");
                let debug_canvas = (*sdl_manager).launch_app("Protosuit Debug", "true", &[])?
                    .context("Failed to get debug canvas")?;
                debug_scene = Some(DebugScene::new(debug_canvas)?);
            }
            "idle" => {
                log::debug!("Creating idle scene");
                let idle_canvas = (*sdl_manager).launch_app("Protosuit Idle", "true", &[])?
                    .context("Failed to get idle canvas")?;
                idle_scene = Some(IdleScene::new(idle_canvas)?);
            }
            _ => unreachable!(), // We validated the scene name above
        }

        Ok(Self {
            sdl_manager,
            window_manager,
            mqtt_handler: Some(mqtt_handler),
            command_rx,
            mqtt_status_rx,
            active_scene: default_scene,
            debug_scene,
            idle_scene,
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

        // Create an interval for updating displays
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
            // Process SDL events
            self.sdl_manager.pump_events();

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
                    log::debug!("MQTT connection status changed to: {}", mqtt_connected);
                    if let Some(debug_scene) = &mut self.debug_scene {
                        debug_scene.set_mqtt_status(mqtt_connected);
                    }
                }
                _ = update_interval.tick() => {
                    match self.active_scene.as_str() {
                        "debug" => {
                            if let Some(debug_scene) = &mut self.debug_scene {
                                if let Err(e) = debug_scene.render() {
                                    log::error!("Failed to render debug scene: {}", e);
                                }
                            }
                        }
                        "idle" => {
                            if let Some(idle_scene) = &mut self.idle_scene {
                                if let Err(e) = idle_scene.render() {
                                    log::error!("Failed to render idle scene: {}", e);
                                }
                            }
                        }
                        _ => {
                            log::error!("Unknown active scene: {}", self.active_scene);
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
                // Add frame delay with synchronous sleep
                _ = tokio::task::spawn_blocking(|| {
                    std::thread::sleep(std::time::Duration::from_millis(10));
                }) => {}
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
        if self.active_scene.is_empty() {
            self.active_scene = name.to_string();
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
        if self.active_scene == name {
            self.active_scene.clear();
        }

        Ok(())
    }

    async fn handle_switch(&mut self, name: &str) -> Result<()> {
        match name {
            "debug" => {
                if self.debug_scene.is_none() {
                    log::debug!("Creating debug scene");
                    let debug_canvas = self.sdl_manager.launch_app("Protosuit Debug", "true", &[])?
                        .context("Failed to get debug canvas")?;
                    self.debug_scene = Some(DebugScene::new(debug_canvas)?);
                }
                self.active_scene = "debug".to_string();
            }
            "idle" => {
                if self.idle_scene.is_none() {
                    log::debug!("Creating idle scene");
                    let idle_canvas = self.sdl_manager.launch_app("Protosuit Idle", "true", &[])?
                        .context("Failed to get idle canvas")?;
                    self.idle_scene = Some(IdleScene::new(idle_canvas)?);
                }
                self.active_scene = "idle".to_string();
            }
            _ => {
                log::error!("Unknown scene: {}", name);
                return Ok(());
            }
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
