// Teensy Menu Controls - Schema-driven UI for Teensy parameters

let teensySchema = null;
let teensyValues = {};

// Nice display names for camelCase param names
const teensyParamLabels = {
    face: 'Face',
    bright: 'Brightness',
    accentBright: 'Accent Brightness',
    microphone: 'Microphone',
    micLevel: 'Mic Level',
    boopSensor: 'Boop Sensor',
    spectrumMirror: 'Spectrum Mirror',
    faceSize: 'Face Size',
    color: 'Color',
    hueF: 'Hue Front',
    hueB: 'Hue Back',
    effect: 'Effect',
};

function handleTeensySchema(payload) {
    try {
        teensySchema = JSON.parse(payload);
        buildTeensyControls();
    } catch (e) {
        console.error('Error parsing Teensy schema:', e);
    }
}

function handleTeensyParamStatus(param, payload) {
    try {
        const data = JSON.parse(payload);
        teensyValues[param] = data;
        updateTeensyControl(param, data);
    } catch (e) {
        console.error('Error parsing Teensy param status:', e);
    }
}

function handleTeensySaved() {
    const btn = document.getElementById('teensySaveBtn');
    if (btn) {
        const orig = btn.textContent;
        btn.textContent = 'Saved!';
        btn.style.borderColor = 'var(--success)';
        btn.style.color = 'var(--success)';
        setTimeout(() => {
            btn.textContent = orig;
            btn.style.borderColor = '';
            btn.style.color = '';
        }, 2000);
    }
}

function buildTeensyControls() {
    const container = document.getElementById('teensyMenuControls');
    if (!container || !teensySchema) return;

    container.innerHTML = '';

    for (const [param, spec] of Object.entries(teensySchema)) {
        const label = teensyParamLabels[param] || param;
        const wrapper = document.createElement('div');
        wrapper.className = 'teensy-param';
        wrapper.id = `teensy-param-${param}`;

        if (spec.type === 'toggle') {
            wrapper.innerHTML = buildToggleControl(param, label, spec);
        } else if (spec.type === 'select') {
            wrapper.innerHTML = buildSelectControl(param, label, spec);
        } else {
            wrapper.innerHTML = buildRangeControl(param, label, spec);
        }

        container.appendChild(wrapper);
    }

    // Apply any values we already have
    for (const [param, data] of Object.entries(teensyValues)) {
        updateTeensyControl(param, data);
    }

    // Build ESP hue override controls
    buildEspHueControls();
}

function buildToggleControl(param, label, spec) {
    return `
        <div class="teensy-param-header">
            <span class="teensy-param-label">${label}</span>
            <span class="teensy-param-value" id="teensy-val-${param}">--</span>
        </div>
        <div class="teensy-toggle-row">
            <button class="teensy-toggle-btn ${param}-off" id="teensy-opt-${param}-0"
                onclick="teensySet('${param}', 0)">${spec.options[0]}</button>
            <button class="teensy-toggle-btn ${param}-on" id="teensy-opt-${param}-1"
                onclick="teensySet('${param}', 1)">${spec.options[1]}</button>
        </div>
    `;
}

function buildSelectControl(param, label, spec) {
    let buttons = '';
    for (let i = 0; i <= spec.max; i++) {
        const optLabel = spec.options[i] || i;
        buttons += `<button class="teensy-select-btn" id="teensy-opt-${param}-${i}"
            onclick="teensySet('${param}', ${i})">${optLabel}</button>`;
    }
    return `
        <div class="teensy-param-header">
            <span class="teensy-param-label">${label}</span>
            <span class="teensy-param-value" id="teensy-val-${param}">--</span>
        </div>
        <div class="teensy-select-grid">${buttons}</div>
    `;
}

function buildRangeControl(param, label, spec) {
    return `
        <div class="teensy-param-header">
            <span class="teensy-param-label">${label}</span>
            <span class="teensy-param-value" id="teensy-val-${param}">--</span>
        </div>
        <input type="range" min="${spec.min}" max="${spec.max}" value="0"
            id="teensy-slider-${param}"
            oninput="teensySliderInput('${param}', ${spec.max}, parseInt(this.value))">
    `;
}

// Throttle slider sends to avoid flooding serial
let teensySliderTimers = {};

function teensySliderInput(param, max, value) {
    document.getElementById('teensy-val-' + param).textContent = value + ' / ' + max;
    if (teensySliderTimers[param]) return;
    teensySet(param, value);
    teensySliderTimers[param] = setTimeout(() => {
        teensySliderTimers[param] = null;
        // Send final value after throttle window
        const slider = document.getElementById('teensy-slider-' + param);
        if (slider) teensySet(param, parseInt(slider.value));
    }, 100);
}

function updateTeensyControl(param, data) {
    const valEl = document.getElementById(`teensy-val-${param}`);
    if (!valEl) return;

    const spec = teensySchema ? teensySchema[param] : null;
    if (!spec) return;

    if (spec.type === 'toggle' || spec.type === 'select') {
        // Update value display
        valEl.textContent = data.label || data.value;

        // Highlight active option
        for (let i = 0; i <= spec.max; i++) {
            const btn = document.getElementById(`teensy-opt-${param}-${i}`);
            if (btn) {
                btn.classList.toggle('active', i === data.value);
            }
        }
    } else {
        // Range slider
        valEl.textContent = data.value + ' / ' + spec.max;
        const slider = document.getElementById(`teensy-slider-${param}`);
        if (slider && document.activeElement !== slider) {
            slider.value = data.value;
        }
    }
}

function teensySet(param, value) {
    sendCommand('protogen/visor/teensy/menu/set',
        JSON.stringify({ param: param, value: value }), true);
}

function teensyRefresh() {
    sendCommand('protogen/visor/teensy/menu/get', '', true);
}

function teensySave() {
    sendCommand('protogen/visor/teensy/menu/save', '', true);
}

// ======== ESP32 LED Strip Hue Overrides ========

let espHueValues = { hueF: -1, hueB: -1 };
let espHueSliderTimers = {};

function handleEspHueStatus(payload) {
    try {
        espHueValues = JSON.parse(payload);
        updateEspHueUI();
    } catch (e) {
        console.error('Error parsing ESP hue status:', e);
    }
}

function buildEspHueControls() {
    const container = document.getElementById('espHueControls');
    if (!container) return;

    container.innerHTML = `
        <div class="teensy-param">
            <div class="teensy-param-header">
                <span class="teensy-param-label">ESP Hue Front</span>
                <span class="teensy-param-value" id="espHueFValue">Follow Teensy</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <label style="display: flex; align-items: center; gap: 4px; font-size: 0.85em; white-space: nowrap; cursor: pointer;">
                    <input type="checkbox" id="espHueFFollow" checked
                        onchange="toggleEspHueFollow('hueF', this.checked)">
                    Follow
                </label>
                <input type="range" id="espHueFSlider" min="0" max="254" value="0" disabled
                    style="flex: 1; opacity: 0.5;"
                    oninput="espHueSliderInput('hueF', parseInt(this.value))">
            </div>
        </div>
        <div class="teensy-param">
            <div class="teensy-param-header">
                <span class="teensy-param-label">ESP Hue Back</span>
                <span class="teensy-param-value" id="espHueBValue">Follow Teensy</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
                <label style="display: flex; align-items: center; gap: 4px; font-size: 0.85em; white-space: nowrap; cursor: pointer;">
                    <input type="checkbox" id="espHueBFollow" checked
                        onchange="toggleEspHueFollow('hueB', this.checked)">
                    Follow
                </label>
                <input type="range" id="espHueBSlider" min="0" max="254" value="0" disabled
                    style="flex: 1; opacity: 0.5;"
                    oninput="espHueSliderInput('hueB', parseInt(this.value))">
            </div>
        </div>
    `;

    updateEspHueUI();
}

function updateEspHueUI() {
    ['hueF', 'hueB'].forEach(param => {
        const suffix = param === 'hueF' ? 'F' : 'B';
        const slider = document.getElementById(`espHue${suffix}Slider`);
        const valEl = document.getElementById(`espHue${suffix}Value`);
        const follow = document.getElementById(`espHue${suffix}Follow`);
        if (!slider || !valEl || !follow) return;

        const isFollow = espHueValues[param] === -1;
        follow.checked = isFollow;
        slider.disabled = isFollow;
        slider.style.opacity = isFollow ? '0.5' : '1';
        if (isFollow) {
            valEl.textContent = 'Follow Teensy';
        } else {
            valEl.textContent = espHueValues[param] + ' / 254';
            if (document.activeElement !== slider) {
                slider.value = espHueValues[param];
            }
        }
    });
}

function sendEspHue() {
    sendCommand('protogen/visor/esp/set/hue',
        JSON.stringify({ hueF: espHueValues.hueF, hueB: espHueValues.hueB }), true);
}

function toggleEspHueFollow(param, checked) {
    espHueValues[param] = checked ? -1 : 0;
    updateEspHueUI();
    sendEspHue();
}

function espHueSliderInput(param, value) {
    const suffix = param === 'hueF' ? 'F' : 'B';
    const valEl = document.getElementById(`espHue${suffix}Value`);
    if (valEl) valEl.textContent = value + ' / 254';

    if (espHueSliderTimers[param]) return;
    espHueValues[param] = value;
    sendEspHue();
    espHueSliderTimers[param] = setTimeout(() => {
        espHueSliderTimers[param] = null;
        const slider = document.getElementById(`espHue${suffix}Slider`);
        if (slider) {
            espHueValues[param] = parseInt(slider.value);
            sendEspHue();
        }
    }, 100);
}
