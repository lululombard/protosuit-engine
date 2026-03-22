// Animation Management

let currentAnimation = null;
let animationsData = {};
let availableAnimations = [];

function sendTransitionConfig() {
    const duration = parseFloat(document.getElementById('transitionDuration').value);
    const shader = document.getElementById('transitionShader').value;
    if (!shader) return;
    const payload = JSON.stringify({ duration, shader });
    sendCommand('protogen/fins/renderer/set/shader/transition', payload, false, true);
}

function handleTransitionConfig(payload) {
    try {
        const data = JSON.parse(payload);
        if (data.duration !== undefined)
            document.getElementById('transitionDuration').value = data.duration;
        if (data.shader !== undefined)
            document.getElementById('transitionShader').value = data.shader;
    } catch (e) {
        console.error('Error parsing transition config:', e);
    }
}

// Handle renderer shader status updates from MQTT
function handleRendererShaderStatus(payload) {
    try {
        const data = JSON.parse(payload);
        availableAnimations = data.available || [];

        // Populate transition shader dropdown
        const select = document.getElementById('transitionShader');
        if (data.transition_shaders && select) {
            const current = select.value;
            select.innerHTML = '';
            data.transition_shaders.forEach(name => {
                const opt = document.createElement('option');
                opt.value = name;
                opt.textContent = name;
                select.appendChild(opt);
            });
            if (current) select.value = current;
        }

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
