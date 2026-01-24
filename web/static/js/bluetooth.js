// Bluetooth Manager - MQTT Interface

let bluetoothMqttClient = null;
let bluetoothIsConnected = false;

// State
let bluetoothScanning = false;
let bluetoothDevices = [];
let bluetoothAssignments = { left: null, right: null };
let bluetoothConnectedDevices = new Set();

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initBluetooth();
    connectToMQTT();
});

// Connect to MQTT
function connectToMQTT() {
    const mqttHost = window.location.hostname || 'localhost';
    const mqttUrl = `ws://${mqttHost}:9001`;

    updateStatus('Connecting...', false);

    bluetoothMqttClient = mqtt.connect(mqttUrl, {
        clientId: 'protosuit-bluetooth-' + Math.random().toString(16).substr(2, 8),
        clean: true,
        reconnectPeriod: 1000
    });

    bluetoothMqttClient.on('connect', () => {
        bluetoothIsConnected = true;
        updateStatus('Connected ✓', true);

        // Subscribe to status topics
        bluetoothMqttClient.subscribe('protogen/fins/bluetoothbridge/status/scanning');
        bluetoothMqttClient.subscribe('protogen/fins/bluetoothbridge/status/devices');
        bluetoothMqttClient.subscribe('protogen/fins/bluetoothbridge/status/assignments');

        console.log('[Bluetooth] Connected to MQTT');
    });

    bluetoothMqttClient.on('message', (topic, message) => {
        handleMQTTMessage(topic, message.toString());
    });

    bluetoothMqttClient.on('error', () => {
        bluetoothIsConnected = false;
        updateStatus('Error ✗', false);
    });

    bluetoothMqttClient.on('close', () => {
        bluetoothIsConnected = false;
        updateStatus('Disconnected ✗', false);
    });

    bluetoothMqttClient.on('reconnect', () => {
        updateStatus('Reconnecting...', false);
    });
}

// Handle MQTT messages
function handleMQTTMessage(topic, payload) {
    try {
        if (topic === 'protogen/fins/bluetoothbridge/status/scanning') {
            bluetoothScanning = JSON.parse(payload);
            updateScanUI();
        }
        else if (topic === 'protogen/fins/bluetoothbridge/status/devices') {
            bluetoothDevices = JSON.parse(payload);
            updateDevicesList();
            updateAssignmentSelects();
        }
        else if (topic === 'protogen/fins/bluetoothbridge/status/assignments') {
            bluetoothAssignments = JSON.parse(payload);
            updateAssignments();
        }
    } catch (e) {
        console.error('[Bluetooth] Error parsing MQTT message:', e);
    }
}

// Update status display
function updateStatus(message, connected) {
    const statusEl = document.getElementById('status');
    statusEl.textContent = message;
    statusEl.className = 'status' + (connected ? ' connected' : '');
}

// Initialize Bluetooth interface
function initBluetooth() {
    // Scan button
    const scanBtn = document.getElementById('scan-btn');
    scanBtn.addEventListener('click', () => {
        if (bluetoothScanning) {
            stopScan();
        } else {
            startScan();
        }
    });

    // Restart Bluetooth button
    const restartBtn = document.getElementById('restart-bluetooth-btn');
    restartBtn.addEventListener('click', () => {
        if (confirm('Restart Bluetooth service? This will disconnect all devices temporarily.')) {
            restartBluetooth();
        }
    });

    // Assignment selects
    const leftSelect = document.getElementById('left-select');
    const rightSelect = document.getElementById('right-select');

    leftSelect.addEventListener('change', (e) => {
        const mac = e.target.value;
        if (mac === '__REMOVE__') {
            removeAssignment('left');
            e.target.value = ''; // Reset select
        } else if (mac) {
            assignController(mac, 'left');
        }
    });

    rightSelect.addEventListener('change', (e) => {
        const mac = e.target.value;
        if (mac === '__REMOVE__') {
            removeAssignment('right');
            e.target.value = ''; // Reset select
        } else if (mac) {
            assignController(mac, 'right');
        }
    });
}

// Start Bluetooth scan
function startScan() {
    if (!bluetoothMqttClient || !bluetoothIsConnected) return;

    bluetoothMqttClient.publish('protogen/fins/bluetoothbridge/scan/start', '');
    console.log('[Bluetooth] Started scanning');
}

// Stop Bluetooth scan
function stopScan() {
    if (!bluetoothMqttClient || !bluetoothIsConnected) return;

    bluetoothMqttClient.publish('protogen/fins/bluetoothbridge/scan/stop', '');
    console.log('[Bluetooth] Stopped scanning');
}

// Connect to device
function connectDevice(mac) {
    if (!bluetoothMqttClient || !bluetoothIsConnected) return;

    const message = JSON.stringify({ mac: mac });
    bluetoothMqttClient.publish('protogen/fins/bluetoothbridge/connect', message);
    console.log('[Bluetooth] Connecting to:', mac);
}

// Disconnect device
function disconnectDevice(mac) {
    if (!bluetoothMqttClient || !bluetoothIsConnected) return;

    const message = JSON.stringify({ mac: mac });
    bluetoothMqttClient.publish('protogen/fins/bluetoothbridge/disconnect', message);
    console.log('[Bluetooth] Disconnecting from:', mac);
}

// Unpair device
function unpairDevice(mac) {
    if (!bluetoothMqttClient || !bluetoothIsConnected) return;

    if (!confirm('Are you sure you want to unpair this device? You will need to pair it again to use it.')) {
        return;
    }

    const message = JSON.stringify({ mac: mac });
    bluetoothMqttClient.publish('protogen/fins/bluetoothbridge/unpair', message);
    console.log('[Bluetooth] Unpairing:', mac);
}

// Assign controller to display
function assignController(mac, display) {
    if (!bluetoothMqttClient || !bluetoothIsConnected) return;

    const message = JSON.stringify({ mac: mac, display: display });
    bluetoothMqttClient.publish('protogen/fins/bluetoothbridge/assign', message);
    console.log('[Bluetooth] Assigned', mac, 'to', display);
}

// Remove controller assignment
function removeAssignment(display) {
    if (!bluetoothMqttClient || !bluetoothIsConnected) return;

    const message = JSON.stringify({ mac: null, display: display });
    bluetoothMqttClient.publish('protogen/fins/bluetoothbridge/assign', message);
    console.log('[Bluetooth] Removed assignment for', display);
}

// Restart Bluetooth service
function restartBluetooth() {
    if (!bluetoothMqttClient || !bluetoothIsConnected) return;

    bluetoothMqttClient.publish('protogen/fins/bluetoothbridge/bluetooth/restart', '');
    console.log('[Bluetooth] Restarting Bluetooth service...');
    
    // Show feedback in scan status
    const scanStatus = document.getElementById('scan-status');
    scanStatus.textContent = 'Restarting Bluetooth service...';
    scanStatus.style.color = 'var(--accent-primary)';
    
    setTimeout(() => {
        scanStatus.textContent = '';
    }, 3000);
}

// Update scan UI
function updateScanUI() {
    const scanBtn = document.getElementById('scan-btn');
    const scanText = document.getElementById('scan-text');
    const scanSpinner = document.getElementById('scan-spinner');
    const scanStatus = document.getElementById('scan-status');

    if (bluetoothScanning) {
        scanBtn.classList.add('scanning');
        scanText.textContent = 'Stop Scan';
        scanSpinner.style.display = 'inline-block';
        scanStatus.textContent = 'Scanning for Bluetooth devices...';
    } else {
        scanBtn.classList.remove('scanning');
        scanText.textContent = 'Start Scan';
        scanSpinner.style.display = 'none';
        scanStatus.textContent = '';
    }
}

// Update devices list
function updateDevicesList() {
    const devicesList = document.getElementById('devices-list');

    if (bluetoothDevices.length === 0) {
        devicesList.innerHTML = '<div class="empty-state">No devices discovered yet. Click "Start Scan" to begin.</div>';
        return;
    }

    // Clear existing list
    devicesList.innerHTML = '';

    // Create device cards
    bluetoothDevices.forEach(device => {
        const card = createDeviceCard(device);
        devicesList.appendChild(card);
    });
}

// Create device card element
function createDeviceCard(device) {
    const card = document.createElement('div');
    card.className = 'device-card' + (device.connected ? ' connected' : '');

    // Device info
    const info = document.createElement('div');
    info.className = 'device-info';

    const name = document.createElement('div');
    name.className = 'device-name';
    name.textContent = device.name;

    const mac = document.createElement('div');
    mac.className = 'device-mac';
    mac.textContent = device.mac;

    const badges = document.createElement('div');
    badges.className = 'device-badges';

    if (device.paired) {
        const pairedBadge = document.createElement('span');
        pairedBadge.className = 'badge paired';
        pairedBadge.textContent = 'Paired';
        badges.appendChild(pairedBadge);
    }

    if (device.connected) {
        const connectedBadge = document.createElement('span');
        connectedBadge.className = 'badge connected';
        connectedBadge.textContent = 'Connected';
        badges.appendChild(connectedBadge);
    }

    info.appendChild(name);
    info.appendChild(mac);
    info.appendChild(badges);

    // Device actions
    const actions = document.createElement('div');
    actions.className = 'device-actions';

    if (device.connected) {
        const disconnectBtn = document.createElement('button');
        disconnectBtn.className = 'btn btn-small disconnect-btn';
        disconnectBtn.textContent = 'Disconnect';
        disconnectBtn.addEventListener('click', () => disconnectDevice(device.mac));
        actions.appendChild(disconnectBtn);
    } else {
        const connectBtn = document.createElement('button');
        connectBtn.className = 'btn btn-small connect-btn';
        connectBtn.textContent = 'Connect';
        connectBtn.addEventListener('click', () => connectDevice(device.mac));
        actions.appendChild(connectBtn);
    }

    // Add unpair button for paired devices
    if (device.paired) {
        const unpairBtn = document.createElement('button');
        unpairBtn.className = 'btn btn-small unpair-btn';
        unpairBtn.textContent = 'Unpair';
        unpairBtn.addEventListener('click', () => unpairDevice(device.mac));
        actions.appendChild(unpairBtn);
    }

    card.appendChild(info);
    card.appendChild(actions);

    return card;
}

// Update assignment selects
function updateAssignmentSelects() {
    const leftSelect = document.getElementById('left-select');
    const rightSelect = document.getElementById('right-select');

    // Get connected devices
    const connectedDevs = bluetoothDevices.filter(d => d.connected);

    // Update both selects
    [leftSelect, rightSelect].forEach(select => {
        const currentValue = select.value;

        // Add default and remove options
        select.innerHTML = `
            <option value="">Select Controller...</option>
            <option value="__REMOVE__">🗑️ Remove Assignment</option>
        `;

        connectedDevs.forEach(device => {
            const option = document.createElement('option');
            option.value = device.mac;
            option.textContent = device.name;
            select.appendChild(option);
        });

        // Restore selection if still valid
        if (currentValue && connectedDevs.some(d => d.mac === currentValue)) {
            select.value = currentValue;
        }
    });
}

// Update assignments display
function updateAssignments() {
    // Update left assignment
    const leftPanel = document.getElementById('left-assignment');
    const leftController = document.getElementById('left-controller');
    const leftSelect = document.getElementById('left-select');

    if (bluetoothAssignments.left) {
        const isConnected = bluetoothAssignments.left.connected !== false; // default to true for backwards compat
        const statusText = isConnected ? '' : ' (disconnected)';
        leftPanel.classList.add('active');
        leftController.classList.add('assigned');
        if (!isConnected) {
            leftController.classList.add('disconnected');
        } else {
            leftController.classList.remove('disconnected');
        }
        leftController.innerHTML = `
            <div class="controller-info">
                <div class="controller-name">${bluetoothAssignments.left.name}${statusText}</div>
                <div class="controller-mac">${bluetoothAssignments.left.mac}</div>
            </div>
        `;
        leftSelect.value = bluetoothAssignments.left.mac;
    } else {
        leftPanel.classList.remove('active');
        leftController.classList.remove('assigned');
        leftController.classList.remove('disconnected');
        leftController.innerHTML = '<div class="no-assignment">No controller assigned</div>';
        leftSelect.value = '';
    }

    // Update right assignment
    const rightPanel = document.getElementById('right-assignment');
    const rightController = document.getElementById('right-controller');
    const rightSelect = document.getElementById('right-select');

    if (bluetoothAssignments.right) {
        const isConnected = bluetoothAssignments.right.connected !== false; // default to true for backwards compat
        const statusText = isConnected ? '' : ' (disconnected)';
        rightPanel.classList.add('active');
        rightController.classList.add('assigned');
        if (!isConnected) {
            rightController.classList.add('disconnected');
        } else {
            rightController.classList.remove('disconnected');
        }
        rightController.innerHTML = `
            <div class="controller-info">
                <div class="controller-name">${bluetoothAssignments.right.name}${statusText}</div>
                <div class="controller-mac">${bluetoothAssignments.right.mac}</div>
            </div>
        `;
        rightSelect.value = bluetoothAssignments.right.mac;
    } else {
        rightPanel.classList.remove('active');
        rightController.classList.remove('assigned');
        rightController.classList.remove('disconnected');
        rightController.innerHTML = '<div class="no-assignment">No controller assigned</div>';
        rightSelect.value = '';
    }
}

// Flash input indicator (for visual feedback when input is received)
function flashInput(display) {
    const controller = document.getElementById(`${display}-controller`);
    if (controller) {
        controller.classList.add('input-active');
        setTimeout(() => {
            controller.classList.remove('input-active');
        }, 300);
    }
}
