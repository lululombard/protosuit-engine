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

        // Request current status from renderer
        // (No request needed - renderer publishes retained status on startup)
    });

    mqttClient.on('message', (topic, message) => {
        const payload = message.toString();
        lastMessages[topic] = payload;
        trackMessageReceived();

        // Update UI based on messages
        if (topic === 'protogen/fins/renderer/status/shader') {
            handleRendererShaderStatus(payload);
            return; // Don't log the full JSON payload
        } else if (topic === 'protogen/fins/renderer/status/uniform') {
            handleRendererUniformStatus(payload);
            return; // Don't log the full JSON payload
        } else if (topic === 'protogen/fins/renderer/status/performance') {
            handleFpsMessage(topic, payload);
            return; // Don't log the full JSON payload
        } else if (topic === 'protogen/fins/launcher/status/audio') {
            handleLauncherAudioStatus(payload);
            return;
        } else if (topic === 'protogen/fins/launcher/status/video') {
            handleLauncherVideoStatus(payload);
            return;
        } else if (topic === 'protogen/fins/launcher/status/exec') {
            handleLauncherExecStatus(payload);
            return;
        } else if (topic === 'protogen/fins/launcher/status/volume') {
            handleLauncherVolumeStatus(payload);
            return;
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
