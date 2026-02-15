// Animation Management

let currentAnimation = null;
let animationsData = {};
let availableAnimations = [];

// Handle renderer shader status updates from MQTT
function handleRendererShaderStatus(payload) {
    try {
        const data = JSON.parse(payload);
        availableAnimations = data.available || [];

        // Load animation metadata and build UI buttons
        if (data.animations) {
            animationsData = {};
            const container = document.getElementById('animationButtons');
            container.innerHTML = '';

            data.animations.forEach(anim => {
                animationsData[anim.id] = anim;

                // Create button dynamically
                const btn = document.createElement('button');
                const emoji = anim.emoji || '';
                const name = anim.name || anim.id;
                btn.textContent = emoji ? `${emoji} ${name}` : name;
                btn.onclick = () => sendExpression(anim.id);
                container.appendChild(btn);
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
