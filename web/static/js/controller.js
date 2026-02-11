// Protosuit Controller - MQTT Input Interface
// Uses shared MQTT connection from mqtt.js

let selectedDisplay = 'left';
let pressedKeys = new Set();

// Keyboard mapping from physical keys to controller keys
const keyboardMapping = {
    'ArrowUp': 'Up',
    'ArrowDown': 'Down',
    'ArrowLeft': 'Left',
    'ArrowRight': 'Right',
    'a': 'a',  // A button
    'b': 'b'   // B button
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    // Get display from URL parameter (e.g., ?display=right)
    const urlParams = new URLSearchParams(window.location.search);
    const displayParam = urlParams.get('display');
    if (displayParam === 'left' || displayParam === 'right') {
        selectedDisplay = displayParam;
    }

    initController();
    setTimeout(connectToMQTT, 100);
});

// Reconnect when Safari restores page from back-forward cache
window.addEventListener('pageshow', (event) => {
    if (event.persisted && !isConnected) {
        if (mqttClient) mqttClient.end(true);
        mqttClient = null;
        setTimeout(connectToMQTT, 100);
    }
});

// Connect to MQTT using shared connection
let _ctrlReconnectTimer = null;

function connectToMQTT() {
    if (mqttClient) return;

    const mqttHost = window.location.hostname || 'localhost';
    const mqttUrl = `ws://${mqttHost}:9001`;

    updateStatus('Connecting...', false);

    const client = mqtt.connect(mqttUrl, {
        clientId: 'protosuit-controller-' + Math.random().toString(16).substr(2, 8),
        clean: true,
        reconnectPeriod: 2000,
        connectTimeout: 5000
    });
    mqttClient = client;

    client.on('connect', () => {
        if (client !== mqttClient) return;
        isConnected = true;
        updateStatus('Connected ✓', true);
    });

    client.on('error', () => {
        if (client !== mqttClient) return;
        isConnected = false;
        updateStatus('Reconnecting...', false);
    });

    client.on('close', () => {
        if (client !== mqttClient) return;
        isConnected = false;
        updateStatus('Reconnecting...', false);
        if (!_ctrlReconnectTimer) {
            _ctrlReconnectTimer = setTimeout(() => {
                _ctrlReconnectTimer = null;
                if (!isConnected) {
                    const old = mqttClient;
                    mqttClient = null;
                    if (old) try { old.end(true); } catch (e) { /* ignore */ }
                    connectToMQTT();
                }
            }, 500);
        }
    });

    client.on('reconnect', () => {
        if (client !== mqttClient) return;
        updateStatus('Reconnecting...', false);
    });
}

// Update status display
function updateStatus(message, connected) {
    const statusEl = document.getElementById('status');
    statusEl.textContent = message;
    statusEl.className = 'status' + (connected ? ' connected' : '');
}

// Initialize controller
function initController() {
    // Display selector
    document.querySelectorAll('.display-btn').forEach(btn => {
        // Set initial active state based on selectedDisplay
        if (btn.dataset.display === selectedDisplay) {
            btn.classList.add('active');
        }

        btn.addEventListener('click', () => {
            selectedDisplay = btn.dataset.display;
            document.querySelectorAll('.display-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });

    // All buttons with data-key
    document.querySelectorAll('[data-key]').forEach(btn => {
        const key = btn.dataset.key;

        btn.addEventListener('mousedown', (e) => {
            e.preventDefault();
            handleKeyPress(key, btn);
        });

        btn.addEventListener('mouseup', (e) => {
            e.preventDefault();
            handleKeyRelease(key, btn);
        });

        btn.addEventListener('mouseleave', () => {
            if (pressedKeys.has(key)) handleKeyRelease(key, btn);
        });

        btn.addEventListener('touchstart', (e) => {
            e.preventDefault();
            handleKeyPress(key, btn);
        });

        btn.addEventListener('touchend', (e) => {
            e.preventDefault();
            handleKeyRelease(key, btn);
        });

        btn.addEventListener('touchcancel', (e) => {
            e.preventDefault();
            handleKeyRelease(key, btn);
        });
    });

    // Prevent scroll on touch
    document.body.addEventListener('touchmove', (e) => e.preventDefault(), { passive: false });

    // Add keyboard event listeners
    document.addEventListener('keydown', handleKeyboardPress);
    document.addEventListener('keyup', handleKeyboardRelease);

    // Ensure the page can receive keyboard input
    document.body.setAttribute('tabindex', '0');
    document.body.focus();

    // Maintain focus when clicking anywhere on the page
    document.addEventListener('click', () => {
        document.body.focus();
    });
}

// Handle key press
function handleKeyPress(key, btn) {
    if (pressedKeys.has(key)) return;

    pressedKeys.add(key);
    btn.classList.add('pressed');
    sendInput(key, 'keydown');
}

// Handle key release
function handleKeyRelease(key, btn) {
    if (!pressedKeys.has(key)) return;

    pressedKeys.delete(key);
    btn.classList.remove('pressed');
    sendInput(key, 'keyup');
}

// Handle keyboard press
function handleKeyboardPress(event) {
    const key = event.key;
    const controllerKey = keyboardMapping[key];

    if (controllerKey) {
        // Prevent default browser behavior for controlled keys
        event.preventDefault();

        // Find the corresponding button element
        const btn = document.querySelector(`[data-key="${controllerKey}"]`);
        if (btn) {
            handleKeyPress(controllerKey, btn);
        }
    }
}

// Handle keyboard release
function handleKeyboardRelease(event) {
    const key = event.key;
    const controllerKey = keyboardMapping[key];

    if (controllerKey) {
        // Prevent default browser behavior for controlled keys
        event.preventDefault();

        // Find the corresponding button element
        const btn = document.querySelector(`[data-key="${controllerKey}"]`);
        if (btn) {
            handleKeyRelease(controllerKey, btn);
        }
    }
}

// Send MQTT input
function sendInput(key, action) {
    if (!mqttClient || !isConnected) return;

    const message = JSON.stringify({
        key: key,
        action: action,
        display: selectedDisplay
    });

    mqttClient.publish('protogen/fins/launcher/input/exec', message);
}

// Release all keys on visibility change
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        pressedKeys.forEach(key => {
            const btn = document.querySelector(`[data-key="${key}"]`);
            if (btn) handleKeyRelease(key, btn);
        });
    }
});

window.addEventListener('blur', () => {
    pressedKeys.forEach(key => {
        const btn = document.querySelector(`[data-key="${key}"]`);
        if (btn) handleKeyRelease(key, btn);
    });
});
