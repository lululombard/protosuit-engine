mod modules;

use anyhow::Result;
use env_logger::Env;
use modules::app_manager::AppManager;

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize logging
    env_logger::Builder::from_env(Env::default().default_filter_or("info"))
        .format_timestamp_millis()
        .init();

    log::info!("Starting Protosuit engine client...");

    // Get MQTT configuration from environment or use defaults
    let mqtt_broker = std::env::var("MQTT_BROKER").unwrap_or_else(|_| "localhost".to_string());
    let mqtt_port = std::env::var("MQTT_PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(1883);

    log::info!("Connecting to MQTT broker {}:{}", mqtt_broker, mqtt_port);

    // Create and run the application manager
    let mut app_manager = AppManager::new(&mqtt_broker, mqtt_port)?;

    // Handle Ctrl+C gracefully
    let (shutdown_tx, mut shutdown_rx) = tokio::sync::oneshot::channel();

    tokio::spawn(async move {
        if let Err(e) = tokio::signal::ctrl_c().await {
            log::error!("Failed to listen for Ctrl+C: {}", e);
            return;
        }
        let _ = shutdown_tx.send(());
    });

    // Run until shutdown signal
    tokio::select! {
        result = app_manager.run() => {
            if let Err(e) = result {
                log::error!("Application manager error: {}", e);
            }
        }
        _ = &mut shutdown_rx => {
            log::info!("Shutdown signal received");
        }
    }

    log::info!("Protosuit engine client shutting down");
    Ok(())
}