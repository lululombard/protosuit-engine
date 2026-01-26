// Networking Manager - MQTT Interface

let networkingMqttClient = null;
let networkingIsConnected = false;

// State
let interfaces = {};
let clientStatus = { connected: false };
let apStatus = { enabled: false, clients: [] };
let scanResults = [];
let scanning = false;


// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initNetworking();
    connectToMQTT();
});

// Connect to MQTT
function connectToMQTT() {
    const mqttHost = window.location.hostname || 'localhost';
    const mqttUrl = `ws://${mqttHost}:9001`;

    updateStatus('Connecting...', false);

    networkingMqttClient = mqtt.connect(mqttUrl, {
        clientId: 'protosuit-networking-' + Math.random().toString(16).substr(2, 8),
        clean: true,
        reconnectPeriod: 1000
    });

    networkingMqttClient.on('connect', () => {
        networkingIsConnected = true;
        updateStatus('Connected', true);

        // Subscribe to status topics
        networkingMqttClient.subscribe('protogen/fins/networkingbridge/status/interfaces');
        networkingMqttClient.subscribe('protogen/fins/networkingbridge/status/client');
        networkingMqttClient.subscribe('protogen/fins/networkingbridge/status/ap');
        networkingMqttClient.subscribe('protogen/fins/networkingbridge/status/scan');
        networkingMqttClient.subscribe('protogen/fins/networkingbridge/status/scanning');
        networkingMqttClient.subscribe('protogen/fins/networkingbridge/status/qrcode');
        networkingMqttClient.subscribe('protogen/fins/networkingbridge/status/connection');

        console.log('[Networking] Connected to MQTT');
    });

    networkingMqttClient.on('message', (topic, message) => {
        handleMQTTMessage(topic, message.toString());
    });

    networkingMqttClient.on('error', () => {
        networkingIsConnected = false;
        updateStatus('Error', false);
    });

    networkingMqttClient.on('close', () => {
        networkingIsConnected = false;
        updateStatus('Disconnected', false);
    });

    networkingMqttClient.on('reconnect', () => {
        updateStatus('Reconnecting...', false);
    });
}

// Handle MQTT messages
function handleMQTTMessage(topic, payload) {
    try {
        if (topic === 'protogen/fins/networkingbridge/status/interfaces') {
            interfaces = JSON.parse(payload);
            updateInterfacesUI();
        }
        else if (topic === 'protogen/fins/networkingbridge/status/client') {
            clientStatus = JSON.parse(payload);
            updateClientStatusUI();
        }
        else if (topic === 'protogen/fins/networkingbridge/status/ap') {
            apStatus = JSON.parse(payload);
            updateAPStatusUI();
        }
        else if (topic === 'protogen/fins/networkingbridge/status/scan') {
            scanResults = JSON.parse(payload);
            updateScanResultsUI();
        }
        else if (topic === 'protogen/fins/networkingbridge/status/scanning') {
            scanning = JSON.parse(payload);
            updateScanningUI();
        }
        else if (topic === 'protogen/fins/networkingbridge/status/qrcode') {
            const data = JSON.parse(payload);
            displayQRCode(data.qrcode);
        }
        else if (topic === 'protogen/fins/networkingbridge/status/connection') {
            const data = JSON.parse(payload);
            handleConnectionResult(data);
        }
    } catch (e) {
        console.error('[Networking] Error parsing MQTT message:', e);
    }
}

// Update status display
function updateStatus(message, connected) {
    const statusEl = document.getElementById('status');
    statusEl.textContent = message;
    statusEl.className = 'status' + (connected ? ' connected' : '');
}

// Initialize UI event handlers
function initNetworking() {
    // Scan button
    document.getElementById('scan-btn').addEventListener('click', startScan);
    
    // Client enable toggle
    document.getElementById('client-enabled').addEventListener('change', (e) => {
        setClientEnabled(e.target.checked);
    });
    
    // AP enable toggle
    document.getElementById('ap-enabled').addEventListener('change', (e) => {
        setAPEnabled(e.target.checked);
    });
    
    // Routing toggle
    document.getElementById('routing-enabled').addEventListener('change', (e) => {
        setRoutingEnabled(e.target.checked);
    });
    
    // Captive portal toggle
    document.getElementById('captive-enabled').addEventListener('change', (e) => {
        setCaptiveEnabled(e.target.checked);
    });
    
    // QR code button
    document.getElementById('qr-btn').addEventListener('click', showQRCode);
    
    // QR modal close
    document.getElementById('qr-modal-close').addEventListener('click', hideQRModal);
    document.getElementById('qr-modal').addEventListener('click', (e) => {
        if (e.target.id === 'qr-modal') hideQRModal();
    });
    
    // Password modal
    document.getElementById('password-modal-close').addEventListener('click', hidePasswordModal);
    document.getElementById('connect-cancel').addEventListener('click', hidePasswordModal);
    document.getElementById('connect-submit').addEventListener('click', submitConnection);
    document.getElementById('connect-password').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') submitConnection();
    });
    document.getElementById('password-modal').addEventListener('click', (e) => {
        if (e.target.id === 'password-modal') hidePasswordModal();
    });
    
    // AP security change - show/hide password field
    document.getElementById('ap-security').addEventListener('change', (e) => {
        updatePasswordVisibility(e.target.value);
    });
    
    // Show password button
    document.querySelectorAll('.show-btn').forEach(btn => {
        btn.addEventListener('click', handleShowClick);
    });
    
    // Save AP config button
    document.getElementById('save-ap-config-btn').addEventListener('click', saveAPConfig);
}

// Update interfaces UI
function updateInterfacesUI() {
    // Client interface
    const clientIface = interfaces['wlan0'] || interfaces[Object.keys(interfaces).find(k => interfaces[k].mode === 'client')];
    if (clientIface) {
        document.getElementById('client-interface').textContent = clientIface.name;
        updateDetectedIndicator('client-detected', clientIface.detected);
        document.getElementById('client-enabled').checked = clientIface.enabled;
    }
    
    // AP interface
    const apIface = interfaces['wlan1'] || interfaces[Object.keys(interfaces).find(k => interfaces[k].mode === 'ap')];
    if (apIface) {
        document.getElementById('ap-interface').textContent = apIface.name;
        updateDetectedIndicator('ap-detected', apIface.detected);
    }
}

// Update detected indicator
function updateDetectedIndicator(elementId, detected) {
    const container = document.getElementById(elementId);
    const indicator = container.querySelector('.status-indicator');
    const text = container.querySelector('span:last-child');
    
    indicator.className = 'status-indicator ' + (detected ? 'detected' : 'not-detected');
    text.textContent = detected ? 'Yes' : 'No';
}

// Update client status UI
function updateClientStatusUI() {
    // Connected indicator
    const connContainer = document.getElementById('client-connected');
    const connIndicator = connContainer.querySelector('.status-indicator');
    const connText = connContainer.querySelector('span:last-child');
    
    connIndicator.className = 'status-indicator ' + (clientStatus.connected ? 'connected' : 'disconnected');
    connText.textContent = clientStatus.connected ? 'Yes' : 'No';
    
    // Connection details
    document.getElementById('client-ssid').textContent = clientStatus.ssid || '--';
    document.getElementById('client-ip').textContent = 
        clientStatus.ip_address ? `${clientStatus.ip_address}/${clientStatus.cidr || 24}` : '--';
    document.getElementById('client-router').textContent = clientStatus.router || '--';
    
    // Signal strength
    updateSignalBars(clientStatus.signal_percent || 0);
    document.getElementById('client-signal-dbm').textContent = 
        clientStatus.connected ? `${clientStatus.signal_dbm || -100} dBm` : '-- dBm';
}

// Update signal bars
function updateSignalBars(percent) {
    const barsContainer = document.getElementById('client-signal-bars');
    const bars = barsContainer.querySelectorAll('.bar');
    
    // Determine how many bars to light up
    let activeBars = 0;
    if (percent > 80) activeBars = 5;
    else if (percent > 60) activeBars = 4;
    else if (percent > 40) activeBars = 3;
    else if (percent > 20) activeBars = 2;
    else if (percent > 0) activeBars = 1;
    
    // Set signal quality class
    barsContainer.classList.remove('weak', 'fair');
    if (percent < 30) barsContainer.classList.add('weak');
    else if (percent < 60) barsContainer.classList.add('fair');
    
    // Update bars
    bars.forEach((bar, index) => {
        bar.classList.toggle('active', index < activeBars);
    });
}

// Track if we've received initial config
let apConfigInitialized = false;

// Update AP status UI
function updateAPStatusUI() {
    // AP enabled toggle
    document.getElementById('ap-enabled').checked = apStatus.enabled;
    
    // Populate form fields with current config (only on first load)
    if (!apConfigInitialized) {
        document.getElementById('ap-ssid').value = apStatus.ssid || 'Protosuit-AP';
        document.getElementById('ap-password').value = apStatus.password || 'protosuit123';
        document.getElementById('ap-ip-cidr').value = apStatus.ip_cidr || '192.168.50.1/24';
        document.getElementById('ap-security').value = apStatus.security || 'wpa2';
        apConfigInitialized = true;
    }
    
    updatePasswordVisibility(document.getElementById('ap-security').value);
    
    // Routing toggles
    document.getElementById('routing-enabled').checked = apStatus.routing_enabled || false;
    document.getElementById('captive-enabled').checked = apStatus.captive_portal_enabled || false;
    
    // Update QR code SSID
    document.getElementById('qr-ssid').textContent = apStatus.ssid || 'Protosuit-AP';
    
    // Connected clients
    updateClientsListUI();
}

// Update password field visibility based on security type
function updatePasswordVisibility(security) {
    const passwordRow = document.getElementById('password-row');
    passwordRow.style.display = (security === 'none') ? 'none' : 'flex';
}

// Update clients list UI
function updateClientsListUI() {
    const container = document.getElementById('ap-clients-list');
    const clients = apStatus.clients || [];
    
    if (clients.length === 0) {
        container.innerHTML = '<div class="empty-state">No clients connected</div>';
        return;
    }
    
    container.innerHTML = clients.map(client => `
        <div class="client-card">
            <div class="client-ip">${client.ip}</div>
            <div class="client-details">
                ${client.hostname ? `<div class="client-detail"><span>hostname:</span> ${client.hostname}</div>` : ''}
                <div class="client-detail"><span>MAC:</span> ${client.mac}</div>
                ${client.vendor && client.vendor !== 'Unknown' ? `<div class="client-detail"><span>vendor:</span> ${client.vendor}</div>` : ''}
            </div>
        </div>
    `).join('');
}

// Update scan results UI
function updateScanResultsUI() {
    const container = document.getElementById('networks-list');
    
    if (scanResults.length === 0) {
        container.innerHTML = '<div class="empty-state">No networks found</div>';
        return;
    }
    
    container.innerHTML = scanResults.map(network => `
        <div class="network-card ${network.connected ? 'connected' : ''}" 
             onclick="handleNetworkClick('${escapeHtml(network.ssid)}', '${network.security}', ${network.connected})">
            <div class="network-info">
                <div class="network-ssid">${escapeHtml(network.ssid)}</div>
                <div class="network-details">
                    <span class="network-security ${network.security.toLowerCase()}">${network.security}</span>
                    <span>${network.frequency}</span>
                </div>
            </div>
            <div class="network-signal">
                ${createSignalBarsHtml(network.signal_percent)}
                <span style="font-size: 11px; color: var(--text-secondary);">${network.signal_dbm} dBm</span>
            </div>
        </div>
    `).join('');
}

// Create signal bars HTML
function createSignalBarsHtml(percent) {
    let activeBars = 0;
    if (percent > 80) activeBars = 5;
    else if (percent > 60) activeBars = 4;
    else if (percent > 40) activeBars = 3;
    else if (percent > 20) activeBars = 2;
    else if (percent > 0) activeBars = 1;
    
    let qualityClass = '';
    if (percent < 30) qualityClass = 'weak';
    else if (percent < 60) qualityClass = 'fair';
    
    return `
        <div class="signal-bars ${qualityClass}">
            ${[1,2,3,4,5].map(i => `<div class="bar ${i <= activeBars ? 'active' : ''}"></div>`).join('')}
        </div>
    `;
}

// Update scanning UI
function updateScanningUI() {
    const scanBtn = document.getElementById('scan-btn');
    const scanText = document.getElementById('scan-text');
    const scanSpinner = document.getElementById('scan-spinner');
    const scanStatus = document.getElementById('scan-status');
    
    if (scanning) {
        scanBtn.classList.add('scanning');
        scanText.textContent = 'Scanning...';
        scanSpinner.style.display = 'inline-block';
        scanStatus.textContent = 'Scanning for networks...';
    } else {
        scanBtn.classList.remove('scanning');
        scanText.textContent = 'Scan';
        scanSpinner.style.display = 'none';
        scanStatus.textContent = scanResults.length > 0 ? `Found ${scanResults.length} networks` : '';
    }
}

// Start Wi-Fi scan
function startScan() {
    if (!networkingMqttClient || !networkingIsConnected) return;
    
    networkingMqttClient.publish('protogen/fins/networkingbridge/scan/start', '');
    console.log('[Networking] Starting scan');
}

// Set client interface enabled
function setClientEnabled(enabled) {
    if (!networkingMqttClient || !networkingIsConnected) return;
    
    networkingMqttClient.publish(
        'protogen/fins/networkingbridge/client/enable',
        JSON.stringify({ enable: enabled })
    );
}

// Set AP enabled
function setAPEnabled(enabled) {
    if (!networkingMqttClient || !networkingIsConnected) return;
    
    networkingMqttClient.publish(
        'protogen/fins/networkingbridge/ap/enable',
        JSON.stringify({ enable: enabled })
    );
}

// Set routing enabled
function setRoutingEnabled(enabled) {
    if (!networkingMqttClient || !networkingIsConnected) return;
    
    networkingMqttClient.publish(
        'protogen/fins/networkingbridge/routing/enable',
        JSON.stringify({ enable: enabled })
    );
}

// Set captive portal enabled
function setCaptiveEnabled(enabled) {
    if (!networkingMqttClient || !networkingIsConnected) return;
    
    networkingMqttClient.publish(
        'protogen/fins/networkingbridge/captive/enable',
        JSON.stringify({ enable: enabled })
    );
}

// Handle network card click
function handleNetworkClick(ssid, security, connected) {
    if (connected) {
        // Already connected - offer to disconnect
        if (confirm(`Disconnect from "${ssid}"?`)) {
            disconnectFromNetwork();
        }
    } else if (security === 'Open') {
        // Open network - connect directly
        connectToNetwork(ssid, '');
    } else {
        // Secured network - show password dialog
        showPasswordModal(ssid);
    }
}

// Show password modal
function showPasswordModal(ssid) {
    document.getElementById('connect-ssid').textContent = ssid;
    document.getElementById('connect-password').value = '';
    document.getElementById('password-modal').classList.add('show');
    document.getElementById('connect-password').focus();
}

// Hide password modal
function hidePasswordModal() {
    document.getElementById('password-modal').classList.remove('show');
}

// Submit connection
function submitConnection() {
    const ssid = document.getElementById('connect-ssid').textContent;
    const password = document.getElementById('connect-password').value;
    
    connectToNetwork(ssid, password);
    hidePasswordModal();
}

// Connect to network
function connectToNetwork(ssid, password) {
    if (!networkingMqttClient || !networkingIsConnected) return;
    
    networkingMqttClient.publish(
        'protogen/fins/networkingbridge/client/connect',
        JSON.stringify({ ssid: ssid, password: password })
    );
    
    showNotification(`Connecting to "${ssid}"...`, 'info');
}

// Disconnect from network
function disconnectFromNetwork() {
    if (!networkingMqttClient || !networkingIsConnected) return;
    
    networkingMqttClient.publish('protogen/fins/networkingbridge/client/disconnect', '');
}

// Handle connection result
function handleConnectionResult(data) {
    if (data.success) {
        showNotification(`Connected to "${data.ssid}"`, 'success');
    } else {
        showNotification(`Failed to connect to "${data.ssid}"`, 'error');
    }
}

// Show QR code modal
function showQRCode() {
    document.getElementById('qr-code-container').innerHTML = '<div class="qr-loading">Generating QR code...</div>';
    document.getElementById('qr-modal').classList.add('show');
    
    // Request QR code
    if (networkingMqttClient && networkingIsConnected) {
        networkingMqttClient.publish('protogen/fins/networkingbridge/qrcode/generate', '');
    }
}

// Hide QR modal
function hideQRModal() {
    document.getElementById('qr-modal').classList.remove('show');
}

// Display QR code
function displayQRCode(dataUrl) {
    document.getElementById('qr-code-container').innerHTML = `<img src="${dataUrl}" alt="Wi-Fi QR Code">`;
}

// Handle show password button click
function handleShowClick(e) {
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

// Mark AP config as changed
function markAPConfigChanged() {
    document.getElementById('apply-ap-config-btn').style.display = 'block';
}

// Save AP configuration
function saveAPConfig() {
    if (!networkingMqttClient || !networkingIsConnected) {
        showNotification('Not connected to server', 'error');
        return;
    }
    
    const ssid = document.getElementById('ap-ssid').value.trim();
    const security = document.getElementById('ap-security').value;
    const password = document.getElementById('ap-password').value;
    const ipCidr = document.getElementById('ap-ip-cidr').value.trim();
    
    // Validate SSID
    if (!ssid || ssid.length === 0) {
        showNotification('SSID cannot be empty', 'error');
        return;
    }
    if (ssid.length > 32) {
        showNotification('SSID must be 32 characters or less', 'error');
        return;
    }
    
    // Validate password based on security type
    if (security === 'wep') {
        if (password.length !== 5 && password.length !== 13) {
            showNotification('WEP password must be exactly 5 or 13 characters', 'error');
            return;
        }
    } else if (security === 'wpa2') {
        if (password.length < 8 || password.length > 63) {
            showNotification('WPA2 password must be 8-63 characters', 'error');
            return;
        }
    }
    
    // Validate IP CIDR
    const cidrRegex = /^(\d{1,3}\.){3}\d{1,3}\/\d{1,2}$/;
    if (!cidrRegex.test(ipCidr)) {
        showNotification('Invalid IP address format (use x.x.x.x/xx)', 'error');
        return;
    }
    
    const config = {
        ssid: ssid,
        security: security,
        password: password,
        ip_cidr: ipCidr
    };
    
    networkingMqttClient.publish(
        'protogen/fins/networkingbridge/ap/config',
        JSON.stringify(config)
    );
    
    showNotification('AP configuration saved', 'success');
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

// Escape HTML helper
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
