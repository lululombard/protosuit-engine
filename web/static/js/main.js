// Protosuit Engine Web Interface - Main Initialization
// This file orchestrates all modules and handles page initialization

// Initialize everything when DOM is ready
document.addEventListener('DOMContentLoaded', function () {
    console.log('Protosuit Engine Web Interface starting...');

    // Start MQTT rate monitor
    startMQTTRateMonitor();

    // Load animation data from server
    loadAnimationsData();

    // Connect to MQTT broker
    connectMQTT();

    // Initialize preview (check if checkbox was restored by browser)
    initPreview();

    // Initialize FPS monitoring
    initFpsMonitoring();

    console.log('✓ Initialization complete');
});
