// FPS Monitor - Handles real-time FPS and resolution monitoring
// Subscribes to MQTT topics for renderer performance data

let fpsData = {
    fps: 0,
    left: { resolution: { width: 0, height: 0 }, render_scale: 1.0 },
    right: { resolution: { width: 0, height: 0 }, render_scale: 1.0 },
    timestamp: 0
};

function handleFpsMessage(topic, message) {
    try {
        const data = JSON.parse(message);

        // Format: { fps: 38.5, timestamp: 1760727334.154344, displays: { left: {...}, right: {...} } }
        fpsData.fps = data.fps;
        fpsData.left.resolution = data.displays.left.resolution;
        fpsData.left.render_scale = data.displays.left.scale;
        fpsData.right.resolution = data.displays.right.resolution;
        fpsData.right.render_scale = data.displays.right.scale;
        fpsData.timestamp = data.timestamp;

        // Update UI
        updateFpsDisplay();

    } catch (error) {
        console.error('Error parsing FPS data:', error);
    }
}

function updateFpsDisplay() {
    // Unified renderer - one global FPS, per-display resolutions
    const fps = fpsData.fps >= 10 ? Math.round(fpsData.fps) : fpsData.fps.toFixed(1);
    const fpsText = `${fps} FPS`;
    const fpsClass = getFpsClass(fpsData.fps);

    // Update renderer FPS (single global value)
    const rendererFpsElement = document.getElementById('rendererFps');
    if (rendererFpsElement) {
        rendererFpsElement.textContent = fpsText;
        rendererFpsElement.className = fpsClass;
    }

    // Update per-display resolutions
    const leftResElement = document.getElementById('leftRes');
    if (leftResElement) {
        leftResElement.textContent = `${fpsData.left.resolution.width}x${fpsData.left.resolution.height}`;
    }

    const rightResElement = document.getElementById('rightRes');
    if (rightResElement) {
        rightResElement.textContent = `${fpsData.right.resolution.width}x${fpsData.right.resolution.height}`;
    }
}

function getFpsClass(fps) {
    if (fps >= 30) return 'value fps-good';
    if (fps >= 25) return 'value fps-ok';
    if (fps >= 15) return 'value fps-poor';
    return 'value fps-bad';
}

// Export functions for global access
window.handleFpsMessage = handleFpsMessage;
