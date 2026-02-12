// Animation Management

let currentAnimation = null;
let animationsData = {};
let availableAnimations = [];

// Handle renderer shader status updates from MQTT
function handleRendererShaderStatus(payload) {
    try {
        const data = JSON.parse(payload);
        availableAnimations = data.available || [];

        // Load animation metadata (uniforms, etc)
        if (data.animations) {
            animationsData = {};
            data.animations.forEach(anim => {
                animationsData[anim.id] = anim;
                console.log('Loaded animation:', anim.id, 'uniforms:', anim.uniforms);
            });
            logMessage(`✓ Loaded ${data.animations.length} animations from renderer`);
        }

        // Update current animation display
        if (data.current) {
            const leftAnim = data.current.left;
            const rightAnim = data.current.right;

            // If both sides show the same animation, display it
            if (leftAnim === rightAnim && leftAnim) {
                handleAnimationChange(leftAnim);
            }
        }
    } catch (error) {
        console.error('Error parsing shader status:', error);
        logMessage(`Error loading animations: ${error.message}`);
    }
}

function handleAnimationChange(animationId) {
    const currentAnimSpan = document.getElementById('currentAnimation');
    if (currentAnimSpan.textContent !== animationId) {
        currentAnimSpan.textContent = animationId;
        currentAnimation = animationId;
        updateUniformControls(animationId);
    }
}

function sendExpression(expression) {
    currentAnimation = expression;
    updateUniformControls(expression);

    // Send to renderer with new JSON format
    const payload = JSON.stringify({
        display: "both",
        name: expression,
        transition_duration: 0.75
    });
    sendCommand('protogen/fins/renderer/set/shader/file', payload);
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
