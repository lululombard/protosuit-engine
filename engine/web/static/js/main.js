// Protosuit Engine Web Interface - Main Initialization
// This file orchestrates all modules and handles page initialization

// Initialize everything when DOM is ready
document.addEventListener('DOMContentLoaded', function () {
    console.log('Protosuit Engine Web Interface starting...');

    // Start MQTT rate monitor
    startMQTTRateMonitor();

    // Connect to MQTT broker (animations will be loaded from renderer status)
    // Small delay helps Safari finish WebSocket setup before connecting
    setTimeout(connectMQTT, 100);

    // Initialize preview (check if checkbox was restored by browser)
    initPreview();

    console.log('✓ Initialization complete');
});

// Reconnect when Safari restores page from back-forward cache
window.addEventListener('pageshow', function (event) {
    if (event.persisted && !isConnected) {
        console.log('Page restored from bfcache, reconnecting MQTT...');
        disconnectMQTT();
        setTimeout(connectMQTT, 100);
    }
});
