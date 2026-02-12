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
