// Bluetooth Manager - MQTT Interface

let bluetoothMqttClient = null;
let bluetoothIsConnected = false;

// State
let bluetoothScanning = false;
let bluetoothDevices = [];
let bluetoothAssignments = { left: null, right: null, presets: null };
let bluetoothConnectedDevices = new Set();
let discoveredAudioDevices = [];  // Discovered BT audio devices from scanning
let audioDevices = [];  // Available PipeWire/PulseAudio sinks
let currentAudioDevice = null;
let comboConfig = {};  // {left: ["BTN_MODE", "BTN_TL"], ...}
let comboEditorSlot = null;  // Currently editing slot
let colorConfig = {};  // {left: [255,255,255], ...}
let actionComboConfig = {};  // {action_id: [buttons], ...}
let actionComboEditorAction = null;  // Currently editing action (null for new)

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initBluetooth();
    setTimeout(connectToMQTT, 100);
});

// Reconnect when Safari restores page from back-forward cache
window.addEventListener('pageshow', (event) => {
    if (event.persisted && !bluetoothIsConnected) {
        if (bluetoothMqttClient) bluetoothMqttClient.end(true);
        bluetoothMqttClient = null;
        setTimeout(connectToMQTT, 100);
    }
});

// Connect to MQTT
let _btReconnectTimer = null;

function connectToMQTT() {
    if (bluetoothMqttClient) return;

    const mqttHost = window.location.hostname || 'localhost';
    const mqttUrl = `ws://${mqttHost}:9001`;

    updateStatus('Connecting...', false);

    const client = mqtt.connect(mqttUrl, {
        clientId: 'protosuit-bluetooth-' + Math.random().toString(16).substr(2, 8),
        clean: true,
        reconnectPeriod: 2000,
        connectTimeout: 5000
    });
    bluetoothMqttClient = client;

    client.on('connect', () => {
        if (client !== bluetoothMqttClient) return;
        bluetoothIsConnected = true;
        updateStatus('Connected ✓', true);

        client.subscribe('protogen/fins/bluetoothbridge/status/scanning');
        client.subscribe('protogen/fins/bluetoothbridge/status/devices');
        client.subscribe('protogen/fins/bluetoothbridge/status/audio_devices');
        client.subscribe('protogen/fins/bluetoothbridge/status/connection');
        client.subscribe('protogen/fins/controllerbridge/status/assignments');
        client.subscribe('protogen/fins/audiobridge/status/audio_devices');
        client.subscribe('protogen/fins/audiobridge/status/audio_device/current');
        client.subscribe('protogen/fins/controllerbridge/status/combo_config');
        client.subscribe('protogen/fins/controllerbridge/status/color_config');
        client.subscribe('protogen/fins/controllerbridge/status/action_combo_config');

        console.log('[Bluetooth] Connected to MQTT');
    });

    client.on('message', (topic, message) => {
        if (client !== bluetoothMqttClient) return;
        handleMQTTMessage(topic, message.toString());
    });

    client.on('error', () => {
        if (client !== bluetoothMqttClient) return;
        bluetoothIsConnected = false;
        updateStatus('Reconnecting...', false);
    });

    client.on('close', () => {
        if (client !== bluetoothMqttClient) return;
        bluetoothIsConnected = false;
        updateStatus('Reconnecting...', false);
        if (!_btReconnectTimer) {
            _btReconnectTimer = setTimeout(() => {
                _btReconnectTimer = null;
                if (!bluetoothIsConnected) {
                    const old = bluetoothMqttClient;
                    bluetoothMqttClient = null;
                    if (old) try { old.end(true); } catch (e) { /* ignore */ }
                    connectToMQTT();
                }
            }, 500);
        }
    });

    client.on('reconnect', () => {
        if (client !== bluetoothMqttClient) return;
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
        else if (topic === 'protogen/fins/controllerbridge/status/assignments') {
            bluetoothAssignments = JSON.parse(payload);
            updateAssignments();
        }
        else if (topic === 'protogen/fins/audiobridge/status/audio_devices') {
            audioDevices = JSON.parse(payload);
            updateAudioDevicesList();
        }
        else if (topic === 'protogen/fins/bluetoothbridge/status/connection') {
            handleConnectionStatus(JSON.parse(payload));
        }
        else if (topic === 'protogen/fins/audiobridge/status/audio_device/current') {
            currentAudioDevice = JSON.parse(payload);
            updateCurrentAudioDevice();
        }
        else if (topic === 'protogen/fins/controllerbridge/status/combo_config') {
            comboConfig = JSON.parse(payload);
            updateComboDisplay();
        }
        else if (topic === 'protogen/fins/controllerbridge/status/color_config') {
            colorConfig = JSON.parse(payload);
            updateColorPickers();
        }
        else if (topic === 'protogen/fins/controllerbridge/status/action_combo_config') {
            actionComboConfig = JSON.parse(payload);
            updateActionComboList();
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

    // Forget Disconnected button
    const forgetBtn = document.getElementById('forget-disconnected-btn');
    forgetBtn.addEventListener('click', () => {
        forgetDisconnected();
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

    const presetsSelect = document.getElementById('presets-select');
    presetsSelect.addEventListener('change', (e) => {
        const mac = e.target.value;
        if (mac === '__REMOVE__') {
            removeAssignment('presets');
            e.target.value = '';
        } else if (mac) {
            assignController(mac, 'presets');
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

    // Combo edit buttons
    document.querySelectorAll('.combo-edit-btn').forEach(btn => {
        btn.addEventListener('click', () => openComboEditor(btn.dataset.slot));
    });
    document.getElementById('combo-editor-cancel').addEventListener('click', closeComboEditor);
    document.getElementById('combo-editor-save').addEventListener('click', saveComboEditor);

    // Color pickers
    document.querySelectorAll('.color-picker').forEach(picker => {
        picker.addEventListener('change', (e) => {
            const slot = e.target.dataset.slot;
            const rgb = hexToRgb(e.target.value);
            if (slot && rgb && bluetoothMqttClient && bluetoothIsConnected) {
                bluetoothMqttClient.publish('protogen/fins/controllerbridge/color/set',
                    JSON.stringify({ slot: slot, color: rgb }));
                console.log('[Bluetooth] Updated color:', slot, rgb);
            }
        });
    });

    // Action combo editor
    document.getElementById('add-action-combo-btn').addEventListener('click', () => openActionComboEditor());
    document.getElementById('action-combo-editor-cancel').addEventListener('click', closeActionComboEditor);
    document.getElementById('action-combo-editor-save').addEventListener('click', saveActionComboEditor);
    document.getElementById('action-combo-editor-delete').addEventListener('click', deleteActionCombo);
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
    bluetoothMqttClient.publish('protogen/fins/controllerbridge/assign', message);
    console.log('[Bluetooth] Assigned', mac, 'to', display);
}

// Remove controller assignment
function removeAssignment(display) {
    if (!bluetoothMqttClient || !bluetoothIsConnected) return;

    const message = JSON.stringify({ mac: null, display: display });
    bluetoothMqttClient.publish('protogen/fins/controllerbridge/assign', message);
    console.log('[Bluetooth] Removed assignment for', display);
}

// Forget disconnected devices
function forgetDisconnected() {
    if (!bluetoothMqttClient || !bluetoothIsConnected) return;

    bluetoothMqttClient.publish('protogen/fins/bluetoothbridge/forget_disconnected', '');
    console.log('[Bluetooth] Forgetting disconnected devices');
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
    }, 500);
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

    if (device.battery !== undefined && device.battery !== null) {
        const batteryBadge = document.createElement('span');
        batteryBadge.className = 'badge battery' + (device.battery <= 20 ? ' battery-low' : '');
        batteryBadge.textContent = `${device.battery <= 10 ? '🪫' : '🔋'} ${device.battery}%`;
        badges.appendChild(batteryBadge);
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
    const presetsSelect = document.getElementById('presets-select');

    // Get connected devices
    const connectedDevs = bluetoothDevices.filter(d => d.connected);

    // Update all selects
    [leftSelect, rightSelect, presetsSelect].forEach(select => {
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

    // Update presets assignment
    const presetsPanel = document.getElementById('presets-assignment');
    const presetsController = document.getElementById('presets-controller');
    const presetsSelect = document.getElementById('presets-select');

    if (bluetoothAssignments.presets) {
        const isConnected = bluetoothAssignments.presets.connected !== false;
        const statusText = isConnected ? '' : ' (disconnected)';
        presetsPanel.classList.add('active');
        presetsController.classList.add('assigned');
        if (!isConnected) {
            presetsController.classList.add('disconnected');
        } else {
            presetsController.classList.remove('disconnected');
        }
        presetsController.innerHTML = `
            <div class="controller-info">
                <div class="controller-name">${bluetoothAssignments.presets.name}${statusText}</div>
                <div class="controller-mac">${bluetoothAssignments.presets.mac}</div>
            </div>
        `;
        presetsSelect.value = bluetoothAssignments.presets.mac;
    } else {
        presetsPanel.classList.remove('active');
        presetsController.classList.remove('assigned');
        presetsController.classList.remove('disconnected');
        presetsController.innerHTML = '<div class="no-assignment">No controller assigned</div>';
        presetsSelect.value = '';
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
    bluetoothMqttClient.publish('protogen/fins/audiobridge/audio/device/set', message);
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

// ======== Assignment Combo Config ========

// Human-readable button names
const BUTTON_LABELS = {
    'BTN_MODE': 'PS',
    'BTN_TL': 'L1',
    'BTN_TR': 'R1',
    'BTN_TL2': 'L2',
    'BTN_TR2': 'R2',
    'ABS_Z': 'L2',
    'ABS_RZ': 'R2',
    'BTN_SOUTH': 'X / A',
    'BTN_EAST': 'O / B',
    'BTN_NORTH': '△ / Y',
    'BTN_WEST': '□ / X',
    'BTN_THUMBL': 'L3',
    'BTN_THUMBR': 'R3',
    'BTN_SELECT': 'Share',
    'BTN_START': 'Options',
    'DPAD_UP': 'D-Up',
    'DPAD_DOWN': 'D-Down',
    'DPAD_LEFT': 'D-Left',
    'DPAD_RIGHT': 'D-Right',
};

// Available buttons for combo editor
const AVAILABLE_BUTTONS = [
    'BTN_MODE', 'BTN_TL', 'BTN_TR', 'BTN_TL2', 'BTN_TR2',
    'BTN_SOUTH', 'BTN_EAST', 'BTN_NORTH', 'BTN_WEST',
    'BTN_THUMBL', 'BTN_THUMBR', 'BTN_SELECT', 'BTN_START',
    'DPAD_UP', 'DPAD_DOWN', 'DPAD_LEFT', 'DPAD_RIGHT',
];

// Update combo display for all slots
function updateComboDisplay() {
    ['left', 'right', 'presets'].forEach(slot => {
        const container = document.getElementById(`combo-${slot}`);
        if (!container) return;
        const buttons = comboConfig[slot] || [];
        if (buttons.length === 0) {
            container.innerHTML = '<span class="combo-none">Not set</span>';
        } else {
            container.innerHTML = buttons
                .map(btn => `<span class="combo-tag">${BUTTON_LABELS[btn] || btn}</span>`)
                .join(' + ');
        }
    });
}

// Open combo editor for a slot
function openComboEditor(slot) {
    comboEditorSlot = slot;
    const editor = document.getElementById('combo-editor');
    const slotLabel = document.getElementById('combo-editor-slot');
    const buttonsContainer = document.getElementById('combo-editor-buttons');

    slotLabel.textContent = slot === 'presets' ? 'Presets' : slot.charAt(0).toUpperCase() + slot.slice(1) + ' Display';

    const currentButtons = new Set(comboConfig[slot] || []);
    buttonsContainer.innerHTML = '';

    AVAILABLE_BUTTONS.forEach(btn => {
        const tag = document.createElement('button');
        tag.className = 'combo-editor-tag' + (currentButtons.has(btn) ? ' selected' : '');
        tag.textContent = BUTTON_LABELS[btn] || btn;
        tag.dataset.button = btn;
        tag.addEventListener('click', () => tag.classList.toggle('selected'));
        buttonsContainer.appendChild(tag);
    });

    editor.style.display = 'block';
}

// Close combo editor
function closeComboEditor() {
    document.getElementById('combo-editor').style.display = 'none';
    comboEditorSlot = null;
}

// Save combo editor
function saveComboEditor() {
    if (!comboEditorSlot || !bluetoothMqttClient || !bluetoothIsConnected) return;

    const selected = [];
    document.querySelectorAll('#combo-editor-buttons .combo-editor-tag.selected').forEach(tag => {
        selected.push(tag.dataset.button);
    });

    const message = JSON.stringify({ slot: comboEditorSlot, buttons: selected });
    bluetoothMqttClient.publish('protogen/fins/controllerbridge/combo/set', message);
    console.log('[Bluetooth] Updated combo:', comboEditorSlot, selected);
    closeComboEditor();
}

// ======== Assignment Color Config ========

function rgbToHex(r, g, b) {
    return '#' + [r, g, b].map(c => c.toString(16).padStart(2, '0')).join('');
}

function hexToRgb(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? [parseInt(result[1], 16), parseInt(result[2], 16), parseInt(result[3], 16)] : null;
}

function updateColorPickers() {
    ['left', 'right', 'presets', 'unassigned'].forEach(slot => {
        const picker = document.getElementById(`color-${slot}`);
        if (!picker) return;
        const rgb = colorConfig[slot];
        if (rgb && rgb.length === 3) {
            picker.value = rgbToHex(rgb[0], rgb[1], rgb[2]);
        }
    });
}

// ======== System Action Combos ========

const ACTION_LABELS = {
    'airplay_toggle': 'AirPlay Toggle',
    'spotify_toggle': 'Spotify Toggle',
    'reboot': 'Reboot',
    'shutdown': 'Shutdown',
    'ap_toggle': 'AP Toggle',
    'esp_restart': 'Restart ESP32',
    'volume_up_1': 'Volume Up 1%',
    'volume_down_1': 'Volume Down 1%',
    'volume_up_5': 'Volume Up 5%',
    'volume_down_5': 'Volume Down 5%',
    'volume_up_10': 'Volume Up 10%',
    'volume_down_10': 'Volume Down 10%',
};

function updateActionComboList() {
    const list = document.getElementById('action-combo-list');
    const entries = Object.entries(actionComboConfig);

    if (entries.length === 0) {
        list.innerHTML = '<div class="empty-state">No action combos configured.</div>';
        return;
    }

    list.innerHTML = '';
    entries.forEach(([actionId, buttons]) => {
        const row = document.createElement('div');
        row.className = 'combo-row';

        const label = document.createElement('div');
        label.className = 'combo-slot-label';
        label.textContent = ACTION_LABELS[actionId] || actionId;

        const btnDisplay = document.createElement('div');
        btnDisplay.className = 'combo-buttons';
        btnDisplay.innerHTML = buttons
            .map(btn => `<span class="combo-tag">${BUTTON_LABELS[btn] || btn}</span>`)
            .join(' + ');

        const editBtn = document.createElement('button');
        editBtn.className = 'btn btn-small combo-edit-btn';
        editBtn.textContent = 'Edit';
        editBtn.addEventListener('click', () => openActionComboEditor(actionId));

        row.appendChild(label);
        row.appendChild(btnDisplay);
        row.appendChild(editBtn);
        list.appendChild(row);
    });
}

function openActionComboEditor(actionId) {
    actionComboEditorAction = actionId || null;
    const editor = document.getElementById('action-combo-editor');
    const actionSelect = document.getElementById('action-combo-action-select');
    const buttonsContainer = document.getElementById('action-combo-editor-buttons');
    const deleteBtn = document.getElementById('action-combo-editor-delete');

    if (actionId && actionComboConfig[actionId]) {
        const buttons = actionComboConfig[actionId];
        actionSelect.value = actionId;
        actionSelect.disabled = true;
        deleteBtn.style.display = 'inline-flex';

        const currentButtons = new Set(buttons);
        buttonsContainer.innerHTML = '';
        AVAILABLE_BUTTONS.forEach(btn => {
            const tag = document.createElement('button');
            tag.className = 'combo-editor-tag' + (currentButtons.has(btn) ? ' selected' : '');
            tag.textContent = BUTTON_LABELS[btn] || btn;
            tag.dataset.button = btn;
            tag.addEventListener('click', () => tag.classList.toggle('selected'));
            buttonsContainer.appendChild(tag);
        });
    } else {
        actionSelect.value = '';
        actionSelect.disabled = false;
        deleteBtn.style.display = 'none';

        buttonsContainer.innerHTML = '';
        AVAILABLE_BUTTONS.forEach(btn => {
            const tag = document.createElement('button');
            tag.className = 'combo-editor-tag';
            tag.textContent = BUTTON_LABELS[btn] || btn;
            tag.dataset.button = btn;
            tag.addEventListener('click', () => tag.classList.toggle('selected'));
            buttonsContainer.appendChild(tag);
        });
    }

    editor.style.display = 'block';
}

function closeActionComboEditor() {
    document.getElementById('action-combo-editor').style.display = 'none';
    document.getElementById('action-combo-action-select').disabled = false;
    actionComboEditorAction = null;
}

function saveActionComboEditor() {
    if (!bluetoothMqttClient || !bluetoothIsConnected) return;

    const actionSelect = document.getElementById('action-combo-action-select');
    const action = actionSelect.value;

    if (!action) return;

    const selected = [];
    document.querySelectorAll('#action-combo-editor-buttons .combo-editor-tag.selected').forEach(tag => {
        selected.push(tag.dataset.button);
    });

    if (selected.length === 0) return;

    const message = JSON.stringify({ action, buttons: selected });
    bluetoothMqttClient.publish('protogen/fins/controllerbridge/action_combo/set', message);
    console.log('[Bluetooth] Updated action combo:', action, selected);
    closeActionComboEditor();
}

function deleteActionCombo() {
    if (!actionComboEditorAction || !bluetoothMqttClient || !bluetoothIsConnected) return;

    const label = ACTION_LABELS[actionComboEditorAction] || actionComboEditorAction;
    if (!confirm(`Delete action combo for "${label}"?`)) return;

    const message = JSON.stringify({ action: actionComboEditorAction, delete: true });
    bluetoothMqttClient.publish('protogen/fins/controllerbridge/action_combo/set', message);
    console.log('[Bluetooth] Deleted action combo:', actionComboEditorAction);
    closeActionComboEditor();
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
