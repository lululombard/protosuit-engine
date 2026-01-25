// Bluetooth Manager - MQTT Interface

let bluetoothMqttClient = null;
let bluetoothIsConnected = false;

// State
let bluetoothScanning = false;
let bluetoothDevices = [];
let bluetoothAssignments = { left: null, right: null };
let bluetoothConnectedDevices = new Set();
let discoveredAudioDevices = [];  // Discovered BT audio devices from scanning
let audioDevices = [];  // Available PipeWire/PulseAudio sinks
let currentAudioDevice = null;

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
        bluetoothMqttClient.subscribe('protogen/fins/bluetoothbridge/status/audio_devices');
        bluetoothMqttClient.subscribe('protogen/fins/bluetoothbridge/status/assignments');
        bluetoothMqttClient.subscribe('protogen/fins/bluetoothbridge/status/connection');
        
        // Subscribe to launcher audio device topics
        bluetoothMqttClient.subscribe('protogen/fins/launcher/status/audio_devices');
        bluetoothMqttClient.subscribe('protogen/fins/launcher/status/audio_device/current');

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
        else if (topic === 'protogen/fins/bluetoothbridge/status/audio_devices') {
            discoveredAudioDevices = JSON.parse(payload);
            updateDevicesList();  // Refresh the discovered devices list
        }
        else if (topic === 'protogen/fins/bluetoothbridge/status/assignments') {
            bluetoothAssignments = JSON.parse(payload);
            updateAssignments();
        }
        else if (topic === 'protogen/fins/launcher/status/audio_devices') {
            audioDevices = JSON.parse(payload);
            updateAudioDevicesList();
        }
        else if (topic === 'protogen/fins/bluetoothbridge/status/connection') {
            handleConnectionStatus(JSON.parse(payload));
        }
        else if (topic === 'protogen/fins/launcher/status/audio_device/current') {
            currentAudioDevice = JSON.parse(payload);
            updateCurrentAudioDevice();
        }
    } catch (e) {
        console.error('[Bluetooth] Error parsing MQTT message:', e);
    }
}

// Handle connection status updates
function handleConnectionStatus(status) {
    const mac = status.mac;
    const deviceName = status.name || mac;
    
    console.log(`[Bluetooth] Connection status: ${mac} -> ${status.status}`);
    
    // Find the device card
    const deviceCard = document.querySelector(`[data-mac="${mac}"]`);
    if (!deviceCard) {
        console.log(`[Bluetooth] Device card not found for ${mac}`);
        return;
    }
    
    // Find connect or disconnect button (either might exist depending on current state)
    const connectBtn = deviceCard.querySelector('.connect-btn') || deviceCard.querySelector('.disconnect-btn');
    if (!connectBtn) {
        console.log(`[Bluetooth] Button not found in device card for ${mac}`);
        return;
    }
    
    if (status.status === 'connecting') {
        console.log(`Connecting to ${deviceName}...`);
        connectBtn.disabled = true;
        connectBtn.textContent = 'Connecting...';
        connectBtn.classList.add('connecting');
        connectBtn.classList.remove('disconnecting');
    } else if (status.status === 'disconnecting') {
        console.log(`Disconnecting from ${deviceName}...`);
        connectBtn.disabled = true;
        connectBtn.textContent = 'Disconnecting...';
        connectBtn.classList.add('disconnecting');
        connectBtn.classList.remove('connecting');
    } else if (status.status === 'connected') {
        console.log(`Connected to ${deviceName}`);
        connectBtn.disabled = false;
        connectBtn.textContent = 'Disconnect';
        connectBtn.classList.remove('connecting', 'disconnecting');
        connectBtn.classList.remove('connect-btn');
        connectBtn.classList.add('disconnect-btn');
    } else if (status.status === 'disconnected') {
        console.log(`Disconnected from ${deviceName}`);
        connectBtn.disabled = false;
        connectBtn.textContent = 'Connect';
        connectBtn.classList.remove('connecting', 'disconnecting');
        connectBtn.classList.remove('disconnect-btn');
        connectBtn.classList.add('connect-btn');
    } else if (status.status === 'failed') {
        console.error(`Failed: ${status.error || 'Unknown error'}`);
        connectBtn.disabled = false;
        connectBtn.textContent = 'Connect';  // Reset to Connect on failure
        connectBtn.classList.remove('connecting', 'disconnecting');
        // Show error notification
        showNotification(`${status.error || 'Operation failed'}`, 'error');
    }
}

// Show notification
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.classList.add('show');
    }, 10);
    
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
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

    // Audio device select
    const audioSelect = document.getElementById('audio-device-select');
    audioSelect.addEventListener('change', (e) => {
        const deviceName = e.target.value;
        if (deviceName) {
            selectAudioDevice(deviceName);
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

    if (bluetoothDevices.length === 0 && discoveredAudioDevices.length === 0) {
        devicesList.innerHTML = '<div class="empty-state">No devices discovered yet. Click "Start Scan" to begin.</div>';
        return;
    }

    // Clear existing list
    devicesList.innerHTML = '';

    // Create gamepad device cards
    if (bluetoothDevices.length > 0) {
        const gamepadHeader = document.createElement('h3');
        gamepadHeader.className = 'device-type-header';
        gamepadHeader.textContent = '🎮 Gamepads';
        devicesList.appendChild(gamepadHeader);
        
        bluetoothDevices.forEach(device => {
            const card = createDeviceCard(device, 'gamepad');
            devicesList.appendChild(card);
        });
    }

    // Create audio device cards
    if (discoveredAudioDevices.length > 0) {
        const audioHeader = document.createElement('h3');
        audioHeader.className = 'device-type-header';
        audioHeader.textContent = '🔊 Audio Devices';
        devicesList.appendChild(audioHeader);
        
        discoveredAudioDevices.forEach(device => {
            const card = createDeviceCard(device, 'audio');
            devicesList.appendChild(card);
        });
    }
}

// Create device card element
function createDeviceCard(device, deviceType) {
    const card = document.createElement('div');
    card.className = 'device-card' + (device.connected ? ' connected' : '');
    card.setAttribute('data-device-type', deviceType);
    card.setAttribute('data-mac', device.mac);

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

// Select audio output device
function selectAudioDevice(deviceName) {
    if (!bluetoothMqttClient || !bluetoothIsConnected) return;

    const message = JSON.stringify({ device: deviceName });
    bluetoothMqttClient.publish('protogen/fins/launcher/audio/device/set', message);
    console.log('[Bluetooth] Selected audio device:', deviceName);
}

// Update audio devices list
function updateAudioDevicesList() {
    const audioSelect = document.getElementById('audio-device-select');
    
    if (!audioDevices || audioDevices.length === 0) {
        audioSelect.innerHTML = '<option value="">No audio devices available</option>';
        return;
    }

    const currentValue = audioSelect.value;

    // Populate dropdown with available devices
    audioSelect.innerHTML = '<option value="">Select Audio Device...</option>';

    audioDevices.forEach(device => {
        const option = document.createElement('option');
        option.value = device.name;
        
        // Add type indicator
        let typeIcon = '';
        if (device.type === 'bluetooth') typeIcon = '🔊 ';
        else if (device.type === 'usb') typeIcon = '🔌 ';
        else if (device.type === 'analog') typeIcon = '🎵 ';
        
        option.textContent = typeIcon + device.description;
        audioSelect.appendChild(option);
    });

    // Restore selection if still valid
    if (currentValue && audioDevices.some(d => d.name === currentValue)) {
        audioSelect.value = currentValue;
    }
}

// Update current audio device display
function updateCurrentAudioDevice() {
    const deviceNameEl = document.getElementById('current-audio-device-name');
    const deviceTypeEl = document.getElementById('current-audio-device-type');
    const audioSelect = document.getElementById('audio-device-select');

    if (currentAudioDevice && currentAudioDevice.device) {
        deviceNameEl.textContent = currentAudioDevice.description || currentAudioDevice.device;
        
        // Show type badge
        let typeBadge = '';
        if (currentAudioDevice.type === 'bluetooth') {
            typeBadge = 'Bluetooth';
        } else if (currentAudioDevice.type === 'usb') {
            typeBadge = 'USB';
        } else if (currentAudioDevice.type === 'analog') {
            typeBadge = 'Built-in';
        } else {
            typeBadge = currentAudioDevice.type;
        }
        deviceTypeEl.textContent = typeBadge;
        deviceTypeEl.className = 'audio-device-type ' + currentAudioDevice.type;

        // Update select to match current device
        audioSelect.value = currentAudioDevice.device;
    } else {
        deviceNameEl.textContent = 'Unknown';
        deviceTypeEl.textContent = '';
        deviceTypeEl.className = 'audio-device-type';
    }
}
