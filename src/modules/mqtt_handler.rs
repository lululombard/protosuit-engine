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
    shutdown_rx: oneshot::Receiver<()>,
}

impl MQTTHandler {
    pub fn new(
        broker: &str,
        port: u16,
        client_id: &str,
        command_tx: mpsc::Sender<AppCommand>,
        connection_status_tx: mpsc::Sender<bool>,
        shutdown_rx: oneshot::Receiver<()>,
    ) -> Result<Self> {
        let mut mqttopts = MqttOptions::new(client_id, broker, port);
        mqttopts.set_keep_alive(Duration::from_secs(5));

        let (client, eventloop) = AsyncClient::new(mqttopts, 10);

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

        loop {
            tokio::select! {
                mqtt_event = self.eventloop.poll() => {
                    match mqtt_event {
                        Ok(Event::Incoming(Packet::Publish(publish))) => {
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
                            self.connection_status_tx.send(true).await
                                .context("Failed to send connection status")?;
                        }
                        Ok(Event::Outgoing(_)) => {
                            log::debug!("Sending PING");
                        }
                        Ok(Event::Incoming(Packet::PingResp)) => {
                            log::debug!("Received PONG");
                        }
                        Err(e) => {
                            log::error!("MQTT Error: {}", e);
                            self.connection_status_tx.send(false).await
                                .context("Failed to send connection status")?;
                            tokio::time::sleep(Duration::from_secs(1)).await;
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
