/**
 * Media Browser functionality
 * Handles browsing and playing media files
 */

let mediaFiles = [];

/**
 * Load media files from the API
 */
async function loadMediaFiles() {
    try {
        const response = await fetch('/api/media');
        const data = await response.json();

        if (data.error) {
            console.error('Media API error:', data.error);
            document.getElementById('mediaList').innerHTML = '<p><em>Error loading media files</em></p>';
            return;
        }

        mediaFiles = data.media;
        renderMediaList();

    } catch (error) {
        console.error('Failed to load media files:', error);
        document.getElementById('mediaList').innerHTML = '<p><em>Failed to load media files</em></p>';
    }
}

/**
 * Render the media file list
 */
function renderMediaList() {
    const mediaList = document.getElementById('mediaList');

    if (mediaFiles.length === 0) {
        mediaList.innerHTML = '<p><em>No media files found</em></p>';
        return;
    }

    // Group files by type
    const videos = mediaFiles.filter(f => f.type === 'video');
    const gifs = mediaFiles.filter(f => f.type === 'gif');
    const audio = mediaFiles.filter(f => f.type === 'audio');
    const images = mediaFiles.filter(f => f.type === 'image');

    let html = '';

    // Videos section
    if (videos.length > 0) {
        html += '<div class="media-section">';
        html += '<h4>📹 Videos</h4>';
        videos.forEach(file => {
            html += `<div class="media-item" onclick="playMedia('${file.path}')">
                <span class="media-icon">🎬</span>
                <span class="media-name">${file.name}</span>
            </div>`;
        });
        html += '</div>';
    }

    // GIFs section
    if (gifs.length > 0) {
        html += '<div class="media-section">';
        html += '<h4>🎞️ GIFs</h4>';
        gifs.forEach(file => {
            html += `<div class="media-item" onclick="playMedia('${file.path}')">
                <span class="media-icon">🎞️</span>
                <span class="media-name">${file.name}</span>
            </div>`;
        });
        html += '</div>';
    }

    // Audio section
    if (audio.length > 0) {
        html += '<div class="media-section">';
        html += '<h4>🎵 Audio</h4>';
        audio.forEach(file => {
            html += `<div class="media-item" onclick="playMedia('${file.path}')">
                <span class="media-icon">🎵</span>
                <span class="media-name">${file.name}</span>
            </div>`;
        });
        html += '</div>';
    }

    // Images section
    if (images.length > 0) {
        html += '<div class="media-section">';
        html += '<h4>🖼️ Images</h4>';
        images.forEach(file => {
            html += `<div class="media-item" onclick="playMedia('${file.path}')">
                <span class="media-icon">🖼️</span>
                <span class="media-name">${file.name}</span>
            </div>`;
        });
        html += '</div>';
    }

    mediaList.innerHTML = html;
}

/**
 * Play a media file
 */
function playMedia(mediaPath) {
    const fadeToBlank = document.getElementById('fadeToBlank').checked;
    const topic = fadeToBlank ? 'protogen/fins/media/blank' : 'protogen/fins/media';

    if (mqttClient && mqttClient.connected) {
        mqttClient.publish(topic, mediaPath);
        logMessage(`Playing media: ${mediaPath} (${fadeToBlank ? 'with blank background' : 'over current shader'})`);
    } else {
        logMessage('Error: Not connected to MQTT');
    }
}

/**
 * Stop media playback
 */
function stopMedia() {
    if (mqttClient && mqttClient.connected) {
        mqttClient.publish('protogen/fins/media', 'stop');
        logMessage('Stopped media playback');
    } else {
        logMessage('Error: Not connected to MQTT');
    }
}

/**
 * Refresh media file list
 */
function refreshMedia() {
    document.getElementById('mediaList').innerHTML = '<p><em>Loading media files...</em></p>';
    loadMediaFiles();
}

// Load media files when the page loads
document.addEventListener('DOMContentLoaded', function () {
    loadMediaFiles();
});
