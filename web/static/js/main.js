// Protosuit Engine Web Interface - Main Initialization
// This file orchestrates all modules and handles page initialization

// Initialize everything when DOM is ready
document.addEventListener('DOMContentLoaded', function () {
    console.log('Protosuit Engine Web Interface starting...');

    // Start MQTT rate monitor
    startMQTTRateMonitor();

    // Connect to MQTT broker (animations will be loaded from renderer status)
    connectMQTT();

    // Initialize preview (check if checkbox was restored by browser)
    initPreview();

    // Initialize FPS monitoring
    initFpsMonitoring();

    console.log('✓ Initialization complete');
});
