use anyhow::{Context, Result};
use rumqttc::{AsyncClient, Event, EventLoop, MqttOptions, Packet, QoS};
use serde::{Deserialize, Serialize};
use std::time::Duration;
use tokio::sync::{mpsc, oneshot};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum AppCommand {
    Start { name: String, command: String, args: Vec<String> },
    Stop { name: String },
    Switch { name: String },
}

pub struct MQTTHandler {
    client: AsyncClient,
    eventloop: EventLoop,
    command_tx: mpsc::Sender<AppCommand>,
    connection_status_tx: mpsc::Sender<bool>,
    pub(crate) shutdown_rx: oneshot::Receiver<()>,
}

impl MQTTHandler {
    pub fn new(
        broker: &str,
        port: u16,
        client_id: &str,
        command_tx: mpsc::Sender<AppCommand>,
        connection_status_tx: mpsc::Sender<bool>,
    ) -> Result<Self> {
        let mut mqttopts = MqttOptions::new(client_id, broker, port);
        mqttopts
            .set_keep_alive(Duration::from_secs(5))
            .set_clean_session(false)  // Enable persistent session
            .set_connection_timeout(Duration::from_secs(10))
            .set_max_packet_size(100 * 1024)
            .set_pending_throttle(Duration::from_millis(100))
            .set_reconnect_opts(rumqttc::ReconnectOptions::Exponential(
                Duration::from_secs(1),    // Initial delay
                Duration::from_secs(60),   // Max delay
                10,                        // Max retries (set to a high number for continuous retry)
            ));

        let (client, eventloop) = AsyncClient::new(mqttopts, 10);
        let (shutdown_tx, shutdown_rx) = oneshot::channel();

        Ok(Self {
            client,
            eventloop,
            command_tx,
            connection_status_tx,
            shutdown_rx,
        })
    }

    pub async fn start(&mut self) -> Result<()> {
        // Subscribe to control topics
        self.client
            .subscribe("app/+", QoS::AtLeastOnce)
            .await
            .context("Failed to subscribe to topics")?;

        let mut consecutive_errors = 0;
        let max_consecutive_errors = 3;

        loop {
            tokio::select! {
                mqtt_event = self.eventloop.poll() => {
                    match mqtt_event {
                        Ok(Event::Incoming(Packet::Publish(publish))) => {
                            consecutive_errors = 0;  // Reset error counter on successful message
                            let topic = publish.topic;
                            let payload = String::from_utf8_lossy(&publish.payload);

                            match topic.as_str() {
                                "app/start" => {
                                    if let Ok(cmd) = serde_json::from_str::<AppCommand>(&payload) {
                                        self.command_tx.send(cmd).await
                                            .context("Failed to send command")?;
                                    }
                                }
                                "app/stop" => {
                                    if let Ok(cmd) = serde_json::from_str::<AppCommand>(&payload) {
                                        self.command_tx.send(cmd).await
                                            .context("Failed to send command")?;
                                    }
                                }
                                "app/switch" => {
                                    if let Ok(cmd) = serde_json::from_str::<AppCommand>(&payload) {
                                        self.command_tx.send(cmd).await
                                            .context("Failed to send command")?;
                                    }
                                }
                                _ => log::warn!("Received message on unknown topic: {}", topic),
                            }
                        }
                        Ok(Event::Incoming(Packet::ConnAck(_))) => {
                            log::info!("Connected to MQTT broker");
                            consecutive_errors = 0;  // Reset error counter on successful connection
                            self.connection_status_tx.send(true).await
                                .context("Failed to send connection status")?;

                            // Resubscribe to topics after reconnection
                            self.client.subscribe("app/+", QoS::AtLeastOnce).await
                                .context("Failed to resubscribe to topics")?;
                        }
                        Ok(Event::Outgoing(_)) => {
                            log::trace!("Sending MQTT packet");
                        }
                        Ok(Event::Incoming(Packet::PingResp)) => {
                            log::trace!("Received MQTT PONG");
                        }
                        Err(e) => {
                            consecutive_errors += 1;
                            log::error!("MQTT Error (attempt {}/{}): {}", consecutive_errors, max_consecutive_errors, e);
                            self.connection_status_tx.send(false).await
                                .context("Failed to send connection status")?;

                            if consecutive_errors >= max_consecutive_errors {
                                log::error!("Too many consecutive MQTT errors, attempting reconnection");
                                tokio::time::sleep(Duration::from_secs(5)).await;
                                consecutive_errors = 0;
                            } else {
                                tokio::time::sleep(Duration::from_secs(1)).await;
                            }
                        }
                        _ => {}
                    }
                }
                _ = &mut self.shutdown_rx => {
                    log::info!("MQTT handler received shutdown signal");
                    self.connection_status_tx.send(false).await
                        .context("Failed to send final connection status")?;
                    break;
                }
            }
        }
        Ok(())
    }

    pub async fn publish_status(&self, app_name: &str, status: &str) -> Result<()> {
        let topic = format!("app/status/{}", app_name);
        self.client
            .publish(topic, QoS::AtLeastOnce, false, status.as_bytes())
            .await
            .context("Failed to publish status")?;
        Ok(())
    }
}
