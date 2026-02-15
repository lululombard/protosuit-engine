// MQTT Connection Management

let mqttClient = null;
let isConnected = false;
let lastMessages = {};
let _reconnectTimer = null;

function connectMQTT() {
    if (mqttClient) return;

    const host = window.location.hostname || 'localhost';
    const client = mqtt.connect(`ws://${host}:9001`, {
        clientId: 'protosuit-web-' + Math.random().toString(16).substr(2, 8),
        clean: true,
        reconnectPeriod: 2000,
        connectTimeout: 5000
    });
    mqttClient = client;

    client.on('connect', () => {
        if (client !== mqttClient) return;
        isConnected = true;
        updateConnectionStatus(true);

        client.subscribe('protogen/fins/#');
        client.subscribe('protogen/visor/#');
    });

    client.on('message', (topic, message) => {
        if (client !== mqttClient) return;
        try {
            trackMessageReceived();

            // Skip binary/high-volume castbridge topics (cover art, log streams)
            if (topic.includes('/playback/cover') || topic.endsWith('/logs')) {
                return;
            }

            const payload = message.toString();
            lastMessages[topic] = payload;

            // Update UI based on messages
            if (topic === 'protogen/fins/renderer/status/shader') {
                handleRendererShaderStatus(payload);
            } else if (topic === 'protogen/fins/renderer/status/uniform') {
                handleRendererUniformStatus(payload);
            } else if (topic === 'protogen/fins/renderer/status/performance') {
                handleFpsMessage(topic, payload);
            } else if (topic === 'protogen/fins/launcher/status/audio') {
                handleLauncherAudioStatus(payload);
            } else if (topic === 'protogen/fins/launcher/status/video') {
                handleLauncherVideoStatus(payload);
            } else if (topic === 'protogen/fins/launcher/status/exec') {
                handleLauncherExecStatus(payload);
            } else if (topic === 'protogen/fins/audiobridge/status/volume') {
                handleLauncherVolumeStatus(payload);
            } else if (topic === 'protogen/fins/systembridge/status/metrics') {
                handleSystemMetrics(payload);
            } else if (topic === 'protogen/fins/systembridge/status/fan_curve') {
                handleSystemFanCurve(payload);
            } else if (topic === 'protogen/fins/systembridge/status/throttle_temp') {
                handleSystemThrottleTemp(payload);
            } else if (topic === 'protogen/visor/esp/status/sensors') {
                handleEspSensorStatus(payload);
            } else if (topic === 'protogen/visor/esp/status/alive') {
                handleEspAliveStatus(payload);
            } else if (topic === 'protogen/visor/esp/status/fancurve') {
                handleFanCurveStatus(payload);
            } else if (topic === 'protogen/visor/teensy/menu/schema') {
                handleTeensySchema(payload);
            } else if (topic.startsWith('protogen/visor/teensy/menu/status/')) {
                const param = topic.replace('protogen/visor/teensy/menu/status/', '');
                handleTeensyParamStatus(param, payload);
            } else if (topic === 'protogen/visor/teensy/menu/saved') {
                handleTeensySaved();
            }
        } catch (e) {
            console.error(`[MQTT] Error handling ${topic}:`, e);
        }
    });

    client.on('error', () => {
        if (client !== mqttClient) return;
        isConnected = false;
        updateConnectionStatus(false, true);
    });

    client.on('close', () => {
        if (client !== mqttClient) return;
        isConnected = false;
        updateConnectionStatus(false, true);
        // Safari iOS suspends WebSockets — library retries on the dead transport.
        // Tear down and rebuild with a fresh WebSocket.
        _scheduleReconnect();
    });

    client.on('reconnect', () => {
        if (client !== mqttClient) return;
        updateConnectionStatus(false, true);
    });
}

function _scheduleReconnect() {
    if (_reconnectTimer) return;
    _reconnectTimer = setTimeout(() => {
        _reconnectTimer = null;
        if (!isConnected) {
            // Null out first so end(true) close events become no-ops via the guard
            const old = mqttClient;
            mqttClient = null;
            if (old) {
                try { old.end(true); } catch (e) { /* ignore */ }
            }
            connectMQTT();
        }
    }, 500);
}

function disconnectMQTT() {
    if (_reconnectTimer) { clearTimeout(_reconnectTimer); _reconnectTimer = null; }
    const old = mqttClient;
    mqttClient = null;
    if (old) {
        try { old.end(true); } catch (e) { /* ignore */ }
    }
    isConnected = false;
    updateConnectionStatus(false);
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
