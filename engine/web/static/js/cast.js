// Cast Manager - MQTT Interface for AirPlay and Spotify Connect

let castMqttClient = null;
let castIsConnected = false;

// State
let airplayStatus = { enabled: false, device_name: 'Protosuit', password: '', running: false };
let spotifyStatus = { enabled: false, device_name: 'Protosuit', username: '', password: '', running: false };
let airplayPlayback = { playing: false, title: '', artist: '', album: '', duration_ms: 0, position_ms: 0 };
let spotifyPlayback = { playing: false, title: '', artist: '', cover_url: '', track_id: '', duration_ms: 0, position_ms: 0 };


// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initCast();
    setTimeout(connectToMQTT, 100);
});

// Reconnect when Safari restores page from back-forward cache
window.addEventListener('pageshow', (event) => {
    if (event.persisted && !castIsConnected) {
        if (castMqttClient) castMqttClient.end(true);
        castMqttClient = null;
        setTimeout(connectToMQTT, 100);
    }
});

// Connect to MQTT
let _castReconnectTimer = null;

function connectToMQTT() {
    if (castMqttClient) return;

    const mqttHost = window.location.hostname || 'localhost';
    const mqttUrl = `ws://${mqttHost}:9001`;

    updateStatus('Connecting...', false);

    const client = mqtt.connect(mqttUrl, {
        clientId: 'protosuit-cast-' + Math.random().toString(16).substr(2, 8),
        clean: true,
        reconnectPeriod: 2000,
        connectTimeout: 5000
    });
    castMqttClient = client;

    client.on('connect', () => {
        if (client !== castMqttClient) return;
        castIsConnected = true;
        updateStatus('Connected', true);

        client.subscribe('protogen/fins/castbridge/status/airplay');
        client.subscribe('protogen/fins/castbridge/status/spotify');
        client.subscribe('protogen/fins/castbridge/status/airplay/playback');
        client.subscribe('protogen/fins/castbridge/status/spotify/playback');
        client.subscribe('protogen/fins/castbridge/status/airplay/playback/cover');

        console.log('[Cast] Connected to MQTT');
    });

    client.on('message', (topic, message) => {
        if (client !== castMqttClient) return;
        if (topic === 'protogen/fins/castbridge/status/airplay/playback/cover') {
            handleAirPlayCover(message);
            return;
        }
        handleMQTTMessage(topic, message.toString());
    });

    client.on('error', () => {
        if (client !== castMqttClient) return;
        castIsConnected = false;
        updateStatus('Reconnecting...', false);
    });

    client.on('close', () => {
        if (client !== castMqttClient) return;
        castIsConnected = false;
        updateStatus('Reconnecting...', false);
        if (!_castReconnectTimer) {
            _castReconnectTimer = setTimeout(() => {
                _castReconnectTimer = null;
                if (!castIsConnected) {
                    const old = castMqttClient;
                    castMqttClient = null;
                    if (old) try { old.end(true); } catch (e) { /* ignore */ }
                    connectToMQTT();
                }
            }, 500);
        }
    });

    client.on('reconnect', () => {
        if (client !== castMqttClient) return;
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
        else if (topic === 'protogen/fins/castbridge/status/airplay/playback') {
            airplayPlayback = JSON.parse(payload);
            updateAirPlayPlaybackUI();
        }
        else if (topic === 'protogen/fins/castbridge/status/spotify/playback') {
            spotifyPlayback = JSON.parse(payload);
            updateSpotifyPlaybackUI();
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

// ========== Playback UI ==========

function formatTime(ms) {
    const totalSec = Math.floor(ms / 1000);
    const min = Math.floor(totalSec / 60);
    const sec = totalSec % 60;
    return `${min}:${sec.toString().padStart(2, '0')}`;
}

let airplayCoverUrl = null;

function handleAirPlayCover(data) {
    // Revoke previous blob URL to avoid memory leaks
    if (airplayCoverUrl) URL.revokeObjectURL(airplayCoverUrl);

    if (!data || data.length === 0) {
        airplayCoverUrl = null;
    } else {
        const blob = new Blob([data], { type: 'image/jpeg' });
        airplayCoverUrl = URL.createObjectURL(blob);
    }

    // Update cover img if now-playing is visible
    const coverImg = document.getElementById('airplay-cover-art');
    if (airplayCoverUrl) {
        coverImg.src = airplayCoverUrl;
        coverImg.style.display = '';
    } else {
        coverImg.style.display = 'none';
    }
}

function updateAirPlayPlaybackUI() {
    const section = document.getElementById('airplay-now-playing');
    const hasTrack = airplayPlayback.playing || airplayPlayback.title;

    section.style.display = hasTrack ? '' : 'none';
    if (!hasTrack) return;

    document.getElementById('airplay-track-title').textContent = airplayPlayback.title || '—';
    document.getElementById('airplay-track-artist').textContent = airplayPlayback.artist || '—';
    document.getElementById('airplay-track-album').textContent = airplayPlayback.album || '';

    const coverImg = document.getElementById('airplay-cover-art');
    if (airplayCoverUrl) {
        coverImg.src = airplayCoverUrl;
        coverImg.style.display = '';
    } else {
        coverImg.style.display = 'none';
    }

    const progress = airplayPlayback.duration_ms > 0
        ? (airplayPlayback.position_ms / airplayPlayback.duration_ms) * 100 : 0;
    document.getElementById('airplay-progress-fill').style.width = `${progress}%`;
    document.getElementById('airplay-time-current').textContent = formatTime(airplayPlayback.position_ms);
    document.getElementById('airplay-time-total').textContent = formatTime(airplayPlayback.duration_ms);
}

function updateSpotifyPlaybackUI() {
    const section = document.getElementById('spotify-now-playing');
    const hasTrack = spotifyPlayback.playing || spotifyPlayback.title;

    section.style.display = hasTrack ? '' : 'none';
    if (!hasTrack) return;

    document.getElementById('spotify-track-title').textContent = spotifyPlayback.title || '—';
    document.getElementById('spotify-track-artist').textContent = spotifyPlayback.artist || '—';

    const coverImg = document.getElementById('spotify-cover-art');
    if (spotifyPlayback.cover_url) {
        coverImg.src = spotifyPlayback.cover_url;
        coverImg.style.display = '';
    } else {
        coverImg.style.display = 'none';
    }

    const progress = spotifyPlayback.duration_ms > 0
        ? (spotifyPlayback.position_ms / spotifyPlayback.duration_ms) * 100 : 0;
    document.getElementById('spotify-progress-fill').style.width = `${progress}%`;
    document.getElementById('spotify-time-current').textContent = formatTime(spotifyPlayback.position_ms);
    document.getElementById('spotify-time-total').textContent = formatTime(spotifyPlayback.duration_ms);
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
    }, 500);
}
