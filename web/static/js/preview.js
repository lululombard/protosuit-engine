// Display Preview Functionality

let previewEnabled = false;
let previewLastFrameTime = 0;
let previewFrameCount = 0;
let previewFpsUpdateInterval = null;

// Check if preview should be enabled on page load (browser may restore checkbox state)
function initPreview() {
    const checkbox = document.getElementById('enablePreview');
    if (checkbox && checkbox.checked) {
        // Checkbox was restored by browser, trigger preview
        togglePreview();
    }
}

function togglePreview() {
    const checkbox = document.getElementById('enablePreview');
    const container = document.getElementById('previewContainer');
    const fpsDisplay = document.getElementById('previewFps');
    const img = document.getElementById('previewImage');

    if (checkbox.checked) {
        // Enable preview
        previewEnabled = true;
        container.style.display = 'block';
        previewFrameCount = 0;
        previewLastFrameTime = Date.now();

        // Use MJPEG stream (efficient, real-time)
        img.src = '/api/stream';

        // Set up frame counting for FPS (estimate based on browser rendering)
        previewFpsUpdateInterval = setInterval(() => {
            const now = Date.now();
            const elapsed = (now - previewLastFrameTime) / 1000;
            if (elapsed > 0) {
                fpsDisplay.textContent = '(MJPEG stream)';
            }
            previewLastFrameTime = now;
        }, 1000);

        logMessage('Preview enabled - MJPEG stream mode');
    } else {
        // Disable preview
        previewEnabled = false;
        container.style.display = 'none';
        fpsDisplay.textContent = '';

        // Clear the image source to stop the stream
        img.src = '';

        if (previewFpsUpdateInterval) {
            clearInterval(previewFpsUpdateInterval);
            previewFpsUpdateInterval = null;
        }
        logMessage('Preview disabled');
    }
}

function updatePreview() {
    if (!previewEnabled) return;

    const img = document.getElementById('previewImage');

    // Create a new image to load in background
    const newImg = new Image();

    // When image loads successfully, update display and fetch next frame immediately
    newImg.onload = function () {
        img.src = newImg.src;
        previewFrameCount++;

        // Immediately request next frame for maximum throughput
        if (previewEnabled) {
            updatePreview();
        }
    };

    // On error, retry after a short delay
    newImg.onerror = function () {
        if (previewEnabled) {
            setTimeout(updatePreview, 500); // Retry after 500ms on error
        }
    };

    // Start loading the image (with timestamp to prevent caching)
    newImg.src = '/api/preview?t=' + Date.now();
}
