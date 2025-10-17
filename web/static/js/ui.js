// UI Utilities - Logging, status updates, rate monitoring

// MQTT rate tracking (separate up/down counters)
let mqttMessagesUp = 0;   // Outgoing messages
let mqttMessagesDown = 0; // Incoming messages
let mqttRateInterval = null;

function logMessage(message, type = 'info') {
    const log = document.getElementById('messageLog');
    const timestamp = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.textContent = `[${timestamp}] ${message}`;
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
}

function clearLog() {
    document.getElementById('messageLog').innerHTML = 'Log cleared...';
}

function startMQTTRateMonitor() {
    mqttRateInterval = setInterval(() => {
        const rateDisplay = document.getElementById('mqttRate');
        rateDisplay.textContent = `MQTT: ↓${mqttMessagesDown}/s ↑${mqttMessagesUp}/s`;

        // Color code based on total rate
        const totalRate = mqttMessagesUp + mqttMessagesDown;
        if (totalRate > 50) {
            rateDisplay.style.color = '#ff6b6b'; // Red for high rate
        } else if (totalRate > 20) {
            rateDisplay.style.color = '#ffd93d'; // Yellow for medium
        } else {
            rateDisplay.style.color = '#4CAF50'; // Green for low
        }

        // Reset counters
        mqttMessagesUp = 0;
        mqttMessagesDown = 0;
    }, 1000);
}

function trackMessageSent() {
    mqttMessagesUp++;
}

function trackMessageReceived() {
    mqttMessagesDown++;
}

function updateConnectionStatus(connected) {
    const statusText = document.getElementById('statusText');
    const connectBtn = document.getElementById('connectBtn');
    const disconnectBtn = document.getElementById('disconnectBtn');

    if (connected) {
        statusText.textContent = 'Connected (MQTT via WebSocket)';
        statusText.style.color = '#51cf66';
        connectBtn.style.display = 'none';
        disconnectBtn.style.display = 'inline-block';
    } else {
        statusText.textContent = 'Disconnected';
        statusText.style.color = '#ff6b6b';
        connectBtn.style.display = 'inline-block';
        disconnectBtn.style.display = 'none';
    }
}
