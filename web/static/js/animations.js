// Animation Management

let currentAnimation = null;
let animationsData = {};

// Load animations data with uniform info
async function loadAnimationsData() {
    try {
        // Add cache-busting parameter
        const response = await fetch('/api/animations?t=' + Date.now());
        const data = await response.json();
        animationsData = {};
        data.animations.forEach(anim => {
            animationsData[anim.id] = anim;
            console.log('Loaded animation:', anim.id, 'uniforms:', anim.uniforms);
        });
        logMessage('Loaded ' + data.animations.length + ' animations');
    } catch (error) {
        logMessage(`Error loading animations: ${error.message}`);
    }
}

function handleAnimationChange(animationId) {
    const currentAnimSpan = document.getElementById('currentAnimation');
    if (currentAnimSpan.textContent !== animationId) {
        currentAnimSpan.textContent = animationId;
        currentAnimation = animationId;
        // Request current uniform values from engine
        requestUniformState();
        updateUniformControls(animationId);
    }
}

function sendExpression(expression) {
    currentAnimation = expression;
    updateUniformControls(expression);
    sendCommand('protogen/fins/sync', expression);
}

function launchDoom() {
    sendCommand('protogen/fins/game', 'doom');
}

function stopGame() {
    sendCommand('protogen/fins/game', 'stop');
}


function sendCustom() {
    const topic = document.getElementById('customTopic').value;
    const payload = document.getElementById('customPayload').value;
    if (topic && payload) {
        sendCommand(topic, payload);
    } else {
        logMessage('Please enter both topic and payload');
    }
}
