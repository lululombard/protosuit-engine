// Cast Manager - MQTT Interface for AirPlay and Spotify Connect

let castMqttClient = null;
let castIsConnected = false;

// State
let airplayStatus = { enabled: false, device_name: 'Protosuit', password: '', running: false };
let spotifyStatus = { enabled: false, device_name: 'Protosuit', username: '', password: '', running: false };


// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initCast();
    connectToMQTT();
});

// Connect to MQTT
function connectToMQTT() {
    const mqttHost = window.location.hostname || 'localhost';
    const mqttUrl = `ws://${mqttHost}:9001`;

    updateStatus('Connecting...', false);

    castMqttClient = mqtt.connect(mqttUrl, {
        clientId: 'protosuit-cast-' + Math.random().toString(16).substr(2, 8),
        clean: true,
        reconnectPeriod: 1000
    });

    castMqttClient.on('connect', () => {
        castIsConnected = true;
        updateStatus('Connected', true);

        // Subscribe to status topics
        castMqttClient.subscribe('protogen/fins/castbridge/status/airplay');
        castMqttClient.subscribe('protogen/fins/castbridge/status/spotify');

        console.log('[Cast] Connected to MQTT');
    });

    castMqttClient.on('message', (topic, message) => {
        handleMQTTMessage(topic, message.toString());
    });

    castMqttClient.on('error', () => {
        castIsConnected = false;
        updateStatus('Error', false);
    });

    castMqttClient.on('close', () => {
        castIsConnected = false;
        updateStatus('Disconnected', false);
    });

    castMqttClient.on('reconnect', () => {
        updateStatus('Reconnecting...', false);
    });
}

// Handle MQTT messages
function handleMQTTMessage(topic, payload) {
    try {
        if (topic === 'protogen/fins/castbridge/status/airplay') {
            airplayStatus = JSON.parse(payload);
            updateAirPlayUI();
        }
        else if (topic === 'protogen/fins/castbridge/status/spotify') {
            spotifyStatus = JSON.parse(payload);
            updateSpotifyUI();
        }
    } catch (e) {
        console.error('[Cast] Error parsing MQTT message:', e);
    }
}

// Update status display
function updateStatus(message, connected) {
    const statusEl = document.getElementById('status');
    statusEl.textContent = message;
    statusEl.className = 'status' + (connected ? ' connected' : '');
}

// Initialize UI event handlers
function initCast() {
    // AirPlay enable toggle
    document.getElementById('airplay-enabled').addEventListener('change', (e) => {
        setAirPlayEnabled(e.target.checked);
    });

    // Spotify enable toggle
    document.getElementById('spotify-enabled').addEventListener('change', (e) => {
        setSpotifyEnabled(e.target.checked);
    });

    // Save AirPlay config button
    document.getElementById('save-airplay-btn').addEventListener('click', saveAirPlayConfig);

    // Save Spotify config button
    document.getElementById('save-spotify-btn').addEventListener('click', saveSpotifyConfig);

    // Password show/hide buttons
    document.querySelectorAll('.show-btn').forEach(btn => {
        btn.addEventListener('click', togglePasswordVisibility);
    });
}

// ========== AirPlay Functions ==========

function setAirPlayEnabled(enabled) {
    if (!castMqttClient) return;

    console.log('[Cast] Setting AirPlay enabled:', enabled);
    castMqttClient.publish(
        'protogen/fins/castbridge/airplay/enable',
        JSON.stringify({ enable: enabled })
    );
}

function saveAirPlayConfig() {
    if (!castMqttClient) return;

    const deviceName = document.getElementById('airplay-name').value || 'Protosuit';
    const password = document.getElementById('airplay-password').value || '';

    console.log('[Cast] Saving AirPlay config:', { deviceName, password: password ? '***' : '' });

    castMqttClient.publish(
        'protogen/fins/castbridge/airplay/config',
        JSON.stringify({
            device_name: deviceName,
            password: password
        })
    );

    showNotification('AirPlay config saved', 'success');
}

function updateAirPlayUI() {
    // Update toggle
    const enabledToggle = document.getElementById('airplay-enabled');
    enabledToggle.checked = airplayStatus.enabled;

    // Update status indicator
    const statusEl = document.getElementById('airplay-status');
    const isRunning = airplayStatus.running;
    statusEl.innerHTML = `
        <span class="status-indicator ${isRunning ? 'running' : 'stopped'}"></span>
        <span>${isRunning ? 'Running' : 'Stopped'}</span>
    `;

    // Update config fields (only if not focused)
    const nameInput = document.getElementById('airplay-name');
    if (document.activeElement !== nameInput) {
        nameInput.value = airplayStatus.device_name || 'Protosuit';
    }

    const passwordInput = document.getElementById('airplay-password');
    if (document.activeElement !== passwordInput) {
        passwordInput.value = airplayStatus.password || '';
    }

    // Update device name display in about section
    const deviceDisplay = document.getElementById('airplay-device-display');
    if (deviceDisplay) {
        deviceDisplay.textContent = airplayStatus.device_name || 'Protosuit';
    }
}

// ========== Spotify Functions ==========

function setSpotifyEnabled(enabled) {
    if (!castMqttClient) return;

    console.log('[Cast] Setting Spotify enabled:', enabled);
    castMqttClient.publish(
        'protogen/fins/castbridge/spotify/enable',
        JSON.stringify({ enable: enabled })
    );
}

function saveSpotifyConfig() {
    if (!castMqttClient) return;

    const deviceName = document.getElementById('spotify-name').value || 'Protosuit';
    const username = document.getElementById('spotify-username').value || '';
    const password = document.getElementById('spotify-password').value || '';

    console.log('[Cast] Saving Spotify config:', { deviceName, username, password: password ? '***' : '' });

    castMqttClient.publish(
        'protogen/fins/castbridge/spotify/config',
        JSON.stringify({
            device_name: deviceName,
            username: username,
            password: password
        })
    );

    showNotification('Spotify config saved', 'success');
}

function updateSpotifyUI() {
    // Update toggle
    const enabledToggle = document.getElementById('spotify-enabled');
    enabledToggle.checked = spotifyStatus.enabled;

    // Update status indicator
    const statusEl = document.getElementById('spotify-status');
    const isRunning = spotifyStatus.running;
    statusEl.innerHTML = `
        <span class="status-indicator ${isRunning ? 'running' : 'stopped'}"></span>
        <span>${isRunning ? 'Running' : 'Stopped'}</span>
    `;

    // Update config fields (only if not focused)
    const nameInput = document.getElementById('spotify-name');
    if (document.activeElement !== nameInput) {
        nameInput.value = spotifyStatus.device_name || 'Protosuit';
    }

    const usernameInput = document.getElementById('spotify-username');
    if (document.activeElement !== usernameInput) {
        usernameInput.value = spotifyStatus.username || '';
    }

    const passwordInput = document.getElementById('spotify-password');
    if (document.activeElement !== passwordInput) {
        passwordInput.value = spotifyStatus.password || '';
    }

    // Update device name display in about section
    const deviceDisplay = document.getElementById('spotify-device-display');
    if (deviceDisplay) {
        deviceDisplay.textContent = spotifyStatus.device_name || 'Protosuit';
    }
}

// ========== Utility Functions ==========

function togglePasswordVisibility(e) {
    const targetId = e.target.dataset.target;
    const input = document.getElementById(targetId);

    if (input.type === 'password') {
        input.type = 'text';
        e.target.textContent = 'Hide';
    } else {
        input.type = 'password';
        e.target.textContent = 'Show';
    }
}

function showNotification(message, type = 'info') {
    // Remove existing notification
    const existing = document.querySelector('.notification');
    if (existing) existing.remove();

    // Create notification
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);

    // Show notification
    setTimeout(() => notification.classList.add('show'), 10);

    // Auto-hide after 3 seconds
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}
