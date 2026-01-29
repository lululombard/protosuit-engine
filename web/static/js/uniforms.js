// Uniform/Slider Controls

// Track current display target for each uniform
const uniformTargets = {};

// Track current uniform values (synced from engine via MQTT)
const currentUniformValues = {};

// Slider damping/smoothing
let sliderMomentum = {}; // Track momentum for each slider
let sliderAnimationFrames = {}; // Track animation frames for smooth movement

// Physics parameters (adjustable via UI)
let dampingCoefficient = 8; // Default damping
let springConstant = 15; // Default spring force
let physicsEnabled = true; // Physics toggle

// Update damping coefficient
function updateDamping(value) {
    dampingCoefficient = parseFloat(value);
    document.getElementById('dampingValue').textContent = value;

    // Reset all momentum to prevent unrealistic jumps
    resetAllMomentum();
}

// Update spring constant
function updateSpring(value) {
    springConstant = parseFloat(value);
    document.getElementById('springValue').textContent = value;

    // Reset all momentum to prevent unrealistic jumps
    resetAllMomentum();
}

// Toggle physics on/off
function togglePhysics(enabled) {
    physicsEnabled = enabled;

    if (!enabled) {
        // Clear all momentum when disabling physics
        clearAllMomentum();
    }
}

// Reset all momentum objects to current slider values
function resetAllMomentum() {
    for (const momentumKey in sliderMomentum) {
        const momentum = sliderMomentum[momentumKey];

        // Cancel any running animation
        if (sliderAnimationFrames[momentumKey]) {
            cancelAnimationFrame(sliderAnimationFrames[momentumKey]);
            delete sliderAnimationFrames[momentumKey];
        }

        // Check if this is a vec3 momentum object (has array values)
        if (Array.isArray(momentum.currentValue)) {
            // Handle vec3 sliders
            const rSlider = document.getElementById(`uniform_${momentumKey}_r`);
            const gSlider = document.getElementById(`uniform_${momentumKey}_g`);
            const bSlider = document.getElementById(`uniform_${momentumKey}_b`);

            if (rSlider && gSlider && bSlider) {
                const currentValue = [
                    parseFloat(rSlider.value),
                    parseFloat(gSlider.value),
                    parseFloat(bSlider.value)
                ];

                momentum.currentValue = currentValue;
                momentum.targetValue = currentValue;
                momentum.velocity = [0, 0, 0];
                momentum.lastTime = performance.now();
            }
        } else {
            // Handle regular float sliders
            const slider = document.getElementById(`uniform_${momentumKey}`);
            if (slider) {
                const currentValue = parseFloat(slider.value);
                momentum.currentValue = currentValue;
                momentum.targetValue = currentValue;
                momentum.velocity = 0;
                momentum.lastTime = performance.now();
            }
        }
    }
}

// Clear all momentum when switching animations
function clearAllMomentum() {
    // Cancel all running animations
    for (const name in sliderAnimationFrames) {
        cancelAnimationFrame(sliderAnimationFrames[name]);
    }

    // Clear all momentum and animation frame tracking
    sliderMomentum = {};
    sliderAnimationFrames = {};
}

// Update uniform controls when animation is selected
function updateUniformControls(animationId) {
    const controlsDiv = document.getElementById('uniformControls');
    const animation = animationsData[animationId];

    console.log('updateUniformControls called for:', animationId, 'animation:', animation);

    // Clear all momentum when switching animations to prevent bugs
    clearAllMomentum();

    if (!animation || !animation.uniforms || animation.uniforms.length === 0) {
        controlsDiv.innerHTML = '<p><em>No controllable parameters for this animation</em></p>';
        return;
    }

    let html = '<p><strong>' + animation.name + ' Parameters:</strong></p>';
    console.log('Rendering', animation.uniforms.length, 'uniforms');

    animation.uniforms.forEach(uniform => {
        const hasPerDisplay = uniform.target === 'per-display';
        const min = uniform.min;
        const max = uniform.max;
        const step = uniform.step;

        html += `<div style="margin: 20px 0; padding: 15px; background: #f5f5f5; border-radius: 5px;">`;
        html += `<div style="margin-bottom: 10px;"><strong>${uniform.name}</strong> (${uniform.type})</div>`;

        // Display target selector (radio buttons styled as buttons)
        if (hasPerDisplay) {
            html += `<div class="display-selector">
                <label>
                    <input type="radio" name="target_${uniform.name}" value="both" checked onchange="updateUniformTarget('${uniform.name}', 'both')">
                    <span>Both</span>
                </label>
                <label>
                    <input type="radio" name="target_${uniform.name}" value="left" onchange="updateUniformTarget('${uniform.name}', 'left')">
                    <span>Left</span>
                </label>
                <label>
                    <input type="radio" name="target_${uniform.name}" value="right" onchange="updateUniformTarget('${uniform.name}', 'right')">
                    <span>Right</span>
                </label>
            </div>`;
        }

        // Slider controls based on type
        if (uniform.type === 'float' && min !== undefined && max !== undefined) {
            const defaultVal = hasPerDisplay ? uniform.value.left : uniform.value;
            // Use current value from engine if available, otherwise use default
            const currentVal = currentUniformValues[uniform.name] !== undefined ? currentUniformValues[uniform.name] : defaultVal;
            // Ultra-fine step for smooth control
            const fineStep = Math.min(step || 0.01, (max - min) / 1000);

            const slider = new Slider(uniform.name, min, max, fineStep, currentVal, 'float', {
                onInput: () => setUniformRealtimeSmooth(uniform.name, 'float'),
                onStart: () => sliderStart(uniform.name),
                onEnd: () => sliderEnd(uniform.name)
            });
            html += slider.generateHTML();
        } else if (uniform.type === 'int' && min !== undefined && max !== undefined) {
            const defaultVal = hasPerDisplay ? uniform.value.left : uniform.value;
            // Use current value from engine if available, otherwise use default
            const currentVal = currentUniformValues[uniform.name] !== undefined ? currentUniformValues[uniform.name] : defaultVal;

            const slider = new Slider(uniform.name, min, max, step || 1, currentVal, 'int', {
                // Use string function names for HTML attributes (no physics for int)
                oninputFunc: `setUniformImmediate('${uniform.name}', 'int')`,
                onmousedownFunc: '', // No momentum tracking
                onmouseupFunc: ''
            });
            html += slider.generateHTML();
        } else if (uniform.type === 'vec3' && min !== undefined && max !== undefined) {
            const components = hasPerDisplay ? uniform.value.left : uniform.value;
            // Use current value from engine if available, otherwise use default
            const currentVec = currentUniformValues[uniform.name] !== undefined ? currentUniformValues[uniform.name] : components;
            const fineStep = Math.min(step || 0.01, (max - min) / 1000);

            const vec3Slider = createVec3Sliders(uniform.name, min, max, fineStep, currentVec, {
                onInput: () => setVec3UniformRealtimeSmooth(uniform.name),
                onStart: (comp) => sliderStart(`${uniform.name}_${comp}`),
                onEnd: (comp) => sliderEnd(`${uniform.name}_${comp}`)
            });
            html += vec3Slider.generateHTML();
        }

        html += `</div>`;
    });

    controlsDiv.innerHTML = html;
}

function updateUniformTarget(uniformName, target) {
    uniformTargets[uniformName] = target;
    console.log(`Target for ${uniformName}: ${target}`);
}

// Slider interaction tracking with momentum
function sliderStart(name) {
    // Skip momentum setup if physics is disabled
    if (!physicsEnabled) {
        return;
    }

    const slider = document.getElementById(`uniform_${name}`);
    const currentValue = parseFloat(slider.value);

    // For vec3 components, use the base uniform name for momentum tracking
    const momentumKey = name.includes('_r') || name.includes('_g') || name.includes('_b')
        ? name.replace(/_[rgb]$/, '')
        : name;

    // Always reset momentum to current slider values to prevent scroll interference
    if (name.includes('_r') || name.includes('_g') || name.includes('_b')) {
        // Vec3 momentum - reset all components
        const uniformName = name.replace(/_[rgb]$/, '');
        const rSlider = document.getElementById(`uniform_${uniformName}_r`);
        const gSlider = document.getElementById(`uniform_${uniformName}_g`);
        const bSlider = document.getElementById(`uniform_${uniformName}_b`);

        sliderMomentum[momentumKey] = {
            dragging: true,
            targetValue: [parseFloat(rSlider.value), parseFloat(gSlider.value), parseFloat(bSlider.value)],
            currentValue: [parseFloat(rSlider.value), parseFloat(gSlider.value), parseFloat(bSlider.value)],
            velocity: [0, 0, 0],
            lastTime: performance.now()
        };
    } else {
        // Float momentum - reset to current value
        sliderMomentum[momentumKey] = {
            dragging: true,
            targetValue: currentValue,
            currentValue: currentValue,
            velocity: 0,
            lastTime: performance.now()
        };
    }

    // Cancel any existing animation
    if (sliderAnimationFrames[momentumKey]) {
        cancelAnimationFrame(sliderAnimationFrames[momentumKey]);
        delete sliderAnimationFrames[momentumKey];
    }
}

function sliderEnd(name) {
    // Skip momentum handling if physics is disabled
    if (!physicsEnabled) {
        return;
    }

    // For vec3 components, use the base uniform name for momentum tracking
    const momentumKey = name.includes('_r') || name.includes('_g') || name.includes('_b')
        ? name.replace(/_[rgb]$/, '')
        : name;

    if (sliderMomentum[momentumKey]) {
        sliderMomentum[momentumKey].dragging = false;
        // Keep momentum for smooth deceleration
    }
}

// Animate slider with momentum and damping
function animateSlider(name, uniformType = 'float') {
    const momentum = sliderMomentum[name];
    if (!momentum) return;

    const currentTime = performance.now();
    const deltaTime = (currentTime - momentum.lastTime) / 1000; // Convert to seconds
    momentum.lastTime = currentTime;

    // Calculate spring force (attracts current value to target)
    const springForce = (momentum.targetValue - momentum.currentValue) * springConstant;

    // Apply damping (resistance to movement)
    const dampingForce = momentum.velocity * -dampingCoefficient;

    // Update velocity with forces
    momentum.velocity += (springForce + dampingForce) * deltaTime;

    // Update current value
    momentum.currentValue += momentum.velocity * deltaTime;

    // Update slider and display
    const slider = document.getElementById(`uniform_${name}`);
    const valueSpan = document.getElementById(`value_${name}`);

    if (slider && valueSpan) {
        slider.value = momentum.currentValue;
        valueSpan.textContent = momentum.currentValue.toFixed(3);

        // Visual feedback
        valueSpan.classList.add('updating');
        setTimeout(() => valueSpan.classList.remove('updating'), 50);

        // Send MQTT command
        sendSliderMQTT(name, momentum.currentValue, uniformType);
        currentUniformValues[name] = momentum.currentValue;
    }

    // Continue animation if still moving or being dragged
    const stillMoving = Math.abs(momentum.velocity) > 0.001 || Math.abs(momentum.targetValue - momentum.currentValue) > 0.001;
    if (stillMoving || momentum.dragging) {
        sliderAnimationFrames[name] = requestAnimationFrame(() => animateSlider(name, uniformType));
    } else {
        delete sliderAnimationFrames[name];
    }
}

// Set uniform value with momentum-based smoothing
function setUniformRealtimeSmooth(uniformName, uniformType) {
    const slider = document.getElementById(`uniform_${uniformName}`);
    const valueSpan = document.getElementById(`value_${uniformName}`);
    const value = parseFloat(slider.value);

    // Visual feedback - flash the value display
    valueSpan.classList.add('updating');
    setTimeout(() => valueSpan.classList.remove('updating'), 50);

    // Update displayed value
    valueSpan.textContent = value.toFixed(3);

    // Track locally for UI consistency
    currentUniformValues[uniformName] = value;

    // Only apply momentum if physics is enabled and user is actively dragging
    if (physicsEnabled) {
        const momentum = sliderMomentum[uniformName];
        if (momentum && momentum.dragging) {
            momentum.targetValue = value;
            // Start animation if not already running
            if (!sliderAnimationFrames[uniformName]) {
                animateSlider(uniformName, uniformType);
            }
        } else {
            // If physics is disabled or not dragging, send MQTT immediately
            sendSliderMQTT(uniformName, value, uniformType);
        }
    } else {
        // If physics is disabled, send MQTT immediately
        sendSliderMQTT(uniformName, value, uniformType);
    }
}

// Send MQTT command for slider (extracted for reuse)
function sendSliderMQTT(uniformName, value, uniformType) {
    const target = uniformTargets[uniformName] || 'both';
    const payload = JSON.stringify({
        display: target,
        name: uniformName,
        type: uniformType,
        value: value
    });
    sendCommand('protogen/fins/renderer/set/shader/uniform', payload, true); // Silent mode
}

// Set uniform value immediately (no physics) - used for int sliders
function setUniformImmediate(uniformName, uniformType) {
    const slider = document.getElementById(`uniform_${uniformName}`);
    const valueSpan = document.getElementById(`value_${uniformName}`);
    const value = uniformType === 'int' ? parseInt(slider.value) : parseFloat(slider.value);

    // Visual feedback
    valueSpan.classList.add('updating');
    setTimeout(() => valueSpan.classList.remove('updating'), 50);

    // Update displayed value (no decimals for int)
    valueSpan.textContent = uniformType === 'int' ? value.toString() : value.toFixed(3);

    // Track locally
    currentUniformValues[uniformName] = value;

    // Send immediately (no physics)
    sendSliderMQTT(uniformName, value, uniformType);
}

// Set vec3 uniform with momentum-based smoothing
function setVec3UniformRealtimeSmooth(uniformName) {
    const r = parseFloat(document.getElementById(`uniform_${uniformName}_r`).value);
    const g = parseFloat(document.getElementById(`uniform_${uniformName}_g`).value);
    const b = parseFloat(document.getElementById(`uniform_${uniformName}_b`).value);

    // Update displayed values with visual feedback
    const rSpan = document.getElementById(`value_${uniformName}_r`);
    const gSpan = document.getElementById(`value_${uniformName}_g`);
    const bSpan = document.getElementById(`value_${uniformName}_b`);

    rSpan.textContent = r.toFixed(3);
    gSpan.textContent = g.toFixed(3);
    bSpan.textContent = b.toFixed(3);

    rSpan.classList.add('updating');
    gSpan.classList.add('updating');
    bSpan.classList.add('updating');
    setTimeout(() => {
        rSpan.classList.remove('updating');
        gSpan.classList.remove('updating');
        bSpan.classList.remove('updating');
    }, 50);

    // Update color preview with smooth transition
    const preview = document.getElementById(`color_preview_${uniformName}`);
    if (preview) {
        preview.style.transition = 'background 0.05s ease-out';
        preview.style.background = `rgb(${r * 255}, ${g * 255}, ${b * 255})`;
    }

    // Track locally for UI consistency
    currentUniformValues[uniformName] = [r, g, b];

    // Only apply momentum if physics is enabled and user is actively dragging
    if (physicsEnabled) {
        const momentum = sliderMomentum[uniformName];
        if (momentum && momentum.dragging) {
            momentum.targetValue = [r, g, b];
            // Start animation if not already running
            if (!sliderAnimationFrames[uniformName]) {
                animateVec3Slider(uniformName);
            }
        } else {
            // If physics is disabled or not dragging, send MQTT immediately
            sendVec3MQTT(uniformName, [r, g, b]);
        }
    } else {
        // If physics is disabled, send MQTT immediately
        sendVec3MQTT(uniformName, [r, g, b]);
    }
}

// Send MQTT command for vec3 slider (extracted for reuse)
function sendVec3MQTT(uniformName, values) {
    const target = uniformTargets[uniformName] || 'both';
    const payload = JSON.stringify({
        display: target,
        name: uniformName,
        type: 'vec3',
        value: values
    });
    sendCommand('protogen/fins/renderer/set/shader/uniform', payload, true); // Silent mode
}

// Animate vec3 slider with momentum and damping
function animateVec3Slider(uniformName) {
    const momentum = sliderMomentum[uniformName];
    if (!momentum) return;

    const currentTime = performance.now();
    const deltaTime = (currentTime - momentum.lastTime) / 1000;
    momentum.lastTime = currentTime;

    const [targetR, targetG, targetB] = momentum.targetValue;
    const [currentR, currentG, currentB] = momentum.currentValue;
    const [velocityR, velocityG, velocityB] = momentum.velocity;

    // Calculate spring forces for each component
    const springForceR = (targetR - currentR) * springConstant;
    const springForceG = (targetG - currentG) * springConstant;
    const springForceB = (targetB - currentB) * springConstant;

    // Apply damping
    const dampingForceR = velocityR * -dampingCoefficient;
    const dampingForceG = velocityG * -dampingCoefficient;
    const dampingForceB = velocityB * -dampingCoefficient;

    // Update velocities
    momentum.velocity[0] += (springForceR + dampingForceR) * deltaTime;
    momentum.velocity[1] += (springForceG + dampingForceG) * deltaTime;
    momentum.velocity[2] += (springForceB + dampingForceB) * deltaTime;

    // Update current values
    momentum.currentValue[0] += momentum.velocity[0] * deltaTime;
    momentum.currentValue[1] += momentum.velocity[1] * deltaTime;
    momentum.currentValue[2] += momentum.velocity[2] * deltaTime;

    const [newR, newG, newB] = momentum.currentValue;

    // Update sliders and displays
    const rSlider = document.getElementById(`uniform_${uniformName}_r`);
    const gSlider = document.getElementById(`uniform_${uniformName}_g`);
    const bSlider = document.getElementById(`uniform_${uniformName}_b`);
    const rSpan = document.getElementById(`value_${uniformName}_r`);
    const gSpan = document.getElementById(`value_${uniformName}_g`);
    const bSpan = document.getElementById(`value_${uniformName}_b`);

    if (rSlider && gSlider && bSlider) {
        rSlider.value = newR;
        gSlider.value = newG;
        bSlider.value = newB;

        if (rSpan) rSpan.textContent = newR.toFixed(3);
        if (gSpan) gSpan.textContent = newG.toFixed(3);
        if (bSpan) bSpan.textContent = newB.toFixed(3);

        // Visual feedback
        [rSpan, gSpan, bSpan].forEach(span => {
            if (span) {
                span.classList.add('updating');
                setTimeout(() => span.classList.remove('updating'), 50);
            }
        });

        // Update color preview
        const preview = document.getElementById(`color_preview_${uniformName}`);
        if (preview) {
            preview.style.background = `rgb(${newR * 255}, ${newG * 255}, ${newB * 255})`;
        }

        // Send MQTT command
        sendVec3MQTT(uniformName, [newR, newG, newB]);
        currentUniformValues[uniformName] = [newR, newG, newB];
    }

    // Continue animation if still moving
    const stillMoving = Math.abs(velocityR) > 0.001 || Math.abs(velocityG) > 0.001 || Math.abs(velocityB) > 0.001 ||
        Math.abs(targetR - currentR) > 0.001 || Math.abs(targetG - currentG) > 0.001 || Math.abs(targetB - currentB) > 0.001;

    if (stillMoving || momentum.dragging) {
        sliderAnimationFrames[uniformName] = requestAnimationFrame(() => animateVec3Slider(uniformName));
    } else {
        delete sliderAnimationFrames[uniformName];
    }
}

// Handle renderer uniform status updates from MQTT
function handleRendererUniformStatus(payload) {
    try {
        const status = JSON.parse(payload);

        // Extract uniform values from the status
        // Status format: { "uniformName": { "type": "float", "value": 1.5 } }
        for (const [uniformName, uniformInfo] of Object.entries(status)) {
            const uniformType = uniformInfo.type;
            const value = uniformInfo.value;

            // Handle both per-display and global values
            let actualValue = value;
            if (typeof value === 'object' && 'left' in value && 'right' in value) {
                // If both displays have same value, use it
                if (JSON.stringify(value.left) === JSON.stringify(value.right)) {
                    actualValue = value.left;
                } else {
                    // Use left value for now (could be enhanced to show both)
                    actualValue = value.left;
                }
            }

            // Update our tracked value
            currentUniformValues[uniformName] = actualValue;

            // Update slider UI (if it exists)
            if (uniformType === 'float') {
                const slider = document.getElementById(`uniform_${uniformName}`);
                const valueSpan = document.getElementById(`value_${uniformName}`);
                if (slider && valueSpan) {
                    slider.value = actualValue;
                    valueSpan.textContent = actualValue.toFixed(3);
                }
            } else if (uniformType === 'int') {
                const slider = document.getElementById(`uniform_${uniformName}`);
                const valueSpan = document.getElementById(`value_${uniformName}`);
                if (slider && valueSpan) {
                    slider.value = actualValue;
                    valueSpan.textContent = actualValue.toString();
                }
            } else if (uniformType === 'vec3' && Array.isArray(actualValue)) {
                const sliderR = document.getElementById(`uniform_${uniformName}_r`);
                const sliderG = document.getElementById(`uniform_${uniformName}_g`);
                const sliderB = document.getElementById(`uniform_${uniformName}_b`);
                const valueR = document.getElementById(`value_${uniformName}_r`);
                const valueG = document.getElementById(`value_${uniformName}_g`);
                const valueB = document.getElementById(`value_${uniformName}_b`);
                const preview = document.getElementById(`color_preview_${uniformName}`);

                if (sliderR && sliderG && sliderB) {
                    sliderR.value = actualValue[0];
                    sliderG.value = actualValue[1];
                    sliderB.value = actualValue[2];
                    if (valueR) valueR.textContent = actualValue[0].toFixed(3);
                    if (valueG) valueG.textContent = actualValue[1].toFixed(3);
                    if (valueB) valueB.textContent = actualValue[2].toFixed(3);
                    if (preview) {
                        preview.style.background = `rgb(${actualValue[0] * 255}, ${actualValue[1] * 255}, ${actualValue[2] * 255})`;
                    }
                }
            }
        }

        console.log(`✓ Received uniform status: ${Object.keys(status).length} uniforms`);
    } catch (e) {
        console.error('Failed to parse renderer uniform status:', e);
    }
}
