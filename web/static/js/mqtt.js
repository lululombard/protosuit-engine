// MQTT Connection Management

let mqttClient = null;
let isConnected = false;
let lastMessages = {};

function connectMQTT() {
    if (mqttClient && isConnected) {
        logMessage('Already connected to MQTT');
        return;
    }

    logMessage('Connecting to MQTT broker via WebSocket...');

    // Connect directly to broker via WebSocket (use current hostname so it works remotely)
    const mqttHost = window.location.hostname || 'localhost';
    const mqttUrl = `ws://${mqttHost}:9001`;
    logMessage(`Connecting to ${mqttUrl}...`);

    mqttClient = mqtt.connect(mqttUrl, {
        clientId: 'protosuit-web-' + Math.random().toString(16).substr(2, 8),
        clean: true,
        reconnectPeriod: 1000
    });

    mqttClient.on('connect', () => {
        isConnected = true;
        updateConnectionStatus(true);
        logMessage('✓ Connected to MQTT broker via WebSocket');

        // Subscribe to status topics
        mqttClient.subscribe('protogen/fins/#', (err) => {
            if (!err) {
                logMessage('✓ Subscribed to protogen/fins/#');
            }
        });
        mqttClient.subscribe('protogen/renderer/#', (err) => {
            if (!err) {
                logMessage('✓ Subscribed to protogen/renderer/#');
            }
        });
        mqttClient.subscribe('protogen/face/#', (err) => {
            if (!err) {
                logMessage('✓ Subscribed to protogen/face/#');
            }
        });

        // Request current status
        mqttClient.publish('protogen/fins/status', 'request');
    });

    mqttClient.on('message', (topic, message) => {
        const payload = message.toString();
        lastMessages[topic] = payload;
        trackMessageReceived();

        // Update UI based on messages
        if (topic === 'protogen/fins/current_animation') {
            handleAnimationChange(payload);
        } else if (topic === 'protogen/fins/uniform/state') {
            handleUniformState(payload);
            return; // Don't log the full JSON payload
        } else if (topic === 'protogen/fins/uniform/changed') {
            handleUniformChanged(payload);
            return; // Don't log the full JSON payload
        } else if (topic === 'protogen/renderer/fps' || (topic.startsWith('protogen/fins/renderer/') && topic.endsWith('/fps'))) {
            // Handle both unified renderer (protogen/renderer/fps) and old per-display format
            handleFpsMessage(topic, payload);
            return; // Don't log the full JSON payload
        }

        logMessage(`← ${topic}: ${payload}`);
    });

    mqttClient.on('error', (err) => {
        logMessage(`✗ MQTT Error: ${err.message}`);
        isConnected = false;
        updateConnectionStatus(false);
    });

    mqttClient.on('close', () => {
        logMessage('✗ MQTT connection closed');
        isConnected = false;
        updateConnectionStatus(false);
    });

    mqttClient.on('reconnect', () => {
        logMessage('⟳ Reconnecting to MQTT...');
    });
}

function disconnectMQTT() {
    if (mqttClient) {
        mqttClient.end();
        mqttClient = null;
        isConnected = false;
        updateConnectionStatus(false);
        logMessage('✓ Disconnected from MQTT');
    }
}

function sendCommand(topic, payload, silent = false) {
    if (!mqttClient || !isConnected) {
        if (!silent) logMessage('✗ Not connected to MQTT broker');
        return;
    }
    mqttClient.publish(topic, payload);
    trackMessageSent();
    if (!silent) {
        logMessage(`→ ${topic}: ${payload}`);
    }
}

function requestUniformState() {
    sendCommand('protogen/fins/uniform/query', 'all');
}
