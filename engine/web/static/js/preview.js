// Display Preview — WebRTC

let previewEnabled = false;
let previewPC = null;      // RTCPeerConnection
let previewWS = null;      // WebSocket for signaling

function initPreview() {
    const checkbox = document.getElementById('enablePreview');
    if (checkbox && checkbox.checked) {
        togglePreview();
    }
}

function togglePreview() {
    const checkbox = document.getElementById('enablePreview');
    const container = document.getElementById('previewContainer');
    const fpsDisplay = document.getElementById('previewFps');

    if (checkbox.checked) {
        previewEnabled = true;
        container.style.display = 'block';
        fpsDisplay.textContent = '(connecting…)';
        startWebRTC();
        logMessage('Preview enabled — WebRTC');
    } else {
        previewEnabled = false;
        container.style.display = 'none';
        fpsDisplay.textContent = '';
        stopWebRTC();
        logMessage('Preview disabled');
    }
}

function startWebRTC() {
    stopWebRTC(); // clean up any previous session

    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const host = window.location.host;
    previewWS = new WebSocket(`${proto}://${host}/ws/preview`);

    previewWS.onmessage = function (event) {
        const msg = JSON.parse(event.data);

        if (msg.type === 'offer') {
            handleOffer(msg.sdp);
        } else if (msg.type === 'ice') {
            handleRemoteICE(msg);
        }
    };

    previewWS.onclose = function () {
        // If preview is still enabled, reconnect after a delay
        if (previewEnabled) {
            const fpsDisplay = document.getElementById('previewFps');
            fpsDisplay.textContent = '(reconnecting…)';
            setTimeout(startWebRTC, 2000);
        }
    };

    previewWS.onerror = function () {
        // onclose will fire after this, triggering reconnect
    };
}

function stopWebRTC() {
    if (previewPC) {
        previewPC.close();
        previewPC = null;
    }
    if (previewWS) {
        const ws = previewWS;
        previewWS = null; // prevent reconnect in onclose
        ws.close();
    }
}

async function handleOffer(sdpText) {
    previewPC = new RTCPeerConnection({
        iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
    });

    // Attach incoming video to <video> element
    previewPC.ontrack = function (event) {
        const video = document.getElementById('previewVideo');
        video.srcObject = event.streams[0];
        document.getElementById('previewFps').textContent = '(streaming)';
    };

    // Send local ICE candidates to server
    previewPC.onicecandidate = function (event) {
        if (event.candidate && previewWS && previewWS.readyState === WebSocket.OPEN) {
            previewWS.send(JSON.stringify({
                type: 'ice',
                sdpMLineIndex: event.candidate.sdpMLineIndex,
                candidate: event.candidate.candidate
            }));
        }
    };

    previewPC.oniceconnectionstatechange = function () {
        const fpsDisplay = document.getElementById('previewFps');
        const state = previewPC ? previewPC.iceConnectionState : 'closed';
        if (state === 'connected' || state === 'completed') {
            fpsDisplay.textContent = '(streaming)';
        } else if (state === 'disconnected' || state === 'failed') {
            fpsDisplay.textContent = '(disconnected)';
        }
    };

    // Set remote offer and create answer
    await previewPC.setRemoteDescription({ type: 'offer', sdp: sdpText });
    const answer = await previewPC.createAnswer();
    await previewPC.setLocalDescription(answer);

    if (previewWS && previewWS.readyState === WebSocket.OPEN) {
        previewWS.send(JSON.stringify({
            type: 'answer',
            sdp: answer.sdp
        }));
    }
}

function handleRemoteICE(msg) {
    if (previewPC && msg.candidate) {
        previewPC.addIceCandidate({
            sdpMLineIndex: msg.sdpMLineIndex,
            candidate: msg.candidate
        });
    }
}
