/**
 * File Browser functionality
 * Handles browsing and playing audio, video, and executables via MQTT
 */

let audioFiles = [];
let videoFiles = [];
let execFiles = [];

/**
 * Handle launcher audio status from MQTT
 */
function handleLauncherAudioStatus(payload) {
    try {
        const data = JSON.parse(payload);
        audioFiles = data.available || [];
        renderFileList();
        console.log(`✓ Loaded ${audioFiles.length} audio files from launcher`);
    } catch (error) {
        console.error('Error parsing launcher audio status:', error);
    }
}

/**
 * Handle launcher video status from MQTT
 */
function handleLauncherVideoStatus(payload) {
    try {
        const data = JSON.parse(payload);
        videoFiles = data.available || [];
        renderFileList();
        console.log(`✓ Loaded ${videoFiles.length} video files from launcher`);
    } catch (error) {
        console.error('Error parsing launcher video status:', error);
    }
}

/**
 * Handle launcher exec status from MQTT
 */
function handleLauncherExecStatus(payload) {
    try {
        const data = JSON.parse(payload);
        execFiles = data.available || [];
        renderFileList();
        console.log(`✓ Loaded ${execFiles.length} executables from launcher`);
    } catch (error) {
        console.error('Error parsing launcher exec status:', error);
    }
}

/**
 * Render the file list
 */
function renderFileList() {
    const fileList = document.getElementById('fileList');

    if (videoFiles.length === 0 && audioFiles.length === 0 && execFiles.length === 0) {
        fileList.innerHTML = '<p><em>No files found</em></p>';
        return;
    }

    let html = '';

    // Videos section
    if (videoFiles.length > 0) {
        html += '<div class="file-section">';
        html += '<h4>📹 Videos</h4>';
        videoFiles.forEach(filename => {
            html += `<div class="file-item" onclick="playVideo('${filename}')">
                <span class="file-icon">🎬</span>
                <span class="file-name">${filename}</span>
            </div>`;
        });
        html += '</div>';
    }

    // Audio section
    if (audioFiles.length > 0) {
        html += '<div class="file-section">';
        html += '<h4>🎵 Audio</h4>';
        audioFiles.forEach(filename => {
            html += `<div class="file-item" onclick="playAudio('${filename}')">
                <span class="file-icon">🎵</span>
                <span class="file-name">${filename}</span>
            </div>`;
        });
        html += '</div>';
    }

    // Executables section
    if (execFiles.length > 0) {
        html += '<div class="file-section">';
        html += '<h4>🎮 Executables</h4>';
        execFiles.forEach(filename => {
            html += `<div class="file-item" onclick="launchExec('${filename}')">
                <span class="file-icon">▶️</span>
                <span class="file-name">${filename}</span>
            </div>`;
        });
        html += '</div>';
    }

    fileList.innerHTML = html;
}

/**
 * Play an audio file
 */
function playAudio(filename) {
    if (mqttClient && mqttClient.connected) {
        mqttClient.publish('protogen/fins/launcher/start/audio', filename);
        logMessage(`Playing audio: ${filename}`);
    } else {
        logMessage('Error: Not connected to MQTT');
    }
}

/**
 * Play a video file
 */
function playVideo(filename) {
    if (mqttClient && mqttClient.connected) {
        const payload = JSON.stringify({
            file: filename
        });
        mqttClient.publish('protogen/fins/launcher/start/video', payload);
        logMessage(`Playing video: ${filename}`);
    } else {
        logMessage('Error: Not connected to MQTT');
    }
}

/**
 * Launch an executable
 */
function launchExec(filename) {
    if (mqttClient && mqttClient.connected) {
        mqttClient.publish('protogen/fins/launcher/start/exec', filename);
        logMessage(`Launching executable: ${filename}`);
    } else {
        logMessage('Error: Not connected to MQTT');
    }
}

/**
 * Kill audio playback (force)
 */
function killAudio() {
    if (mqttClient && mqttClient.connected) {
        mqttClient.publish('protogen/fins/launcher/kill/audio', 'all');
        logMessage('Killed all audio playback');
    } else {
        logMessage('Error: Not connected to MQTT');
    }
}

/**
 * Kill video playback (force)
 */
function killVideo() {
    if (mqttClient && mqttClient.connected) {
        mqttClient.publish('protogen/fins/launcher/kill/video', '');
        logMessage('Killed video playback');
    } else {
        logMessage('Error: Not connected to MQTT');
    }
}

/**
 * Kill executable (force)
 */
function killExec() {
    if (mqttClient && mqttClient.connected) {
        mqttClient.publish('protogen/fins/launcher/kill/exec', '');
        logMessage('Killed executable');
    } else {
        logMessage('Error: Not connected to MQTT');
    }
}

/**
 * Refresh file list
 */
function refreshFiles() {
    document.getElementById('fileList').innerHTML = '<p><em>Waiting for launcher status...</em></p>';
    // Files will be loaded automatically when MQTT status messages arrive
    if (mqttClient && mqttClient.connected) {
        mqttClient.publish('protogen/fins/launcher/config/reload', '');
    }
}

// Files will be loaded automatically from MQTT status messages
// No need to load on DOMContentLoaded - they come from the launcher
