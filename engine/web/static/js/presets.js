// Preset Management

let presetsData = [];
let activePreset = null;
let defaultPreset = null;
let editingPreset = null;

function handlePresetsStatus(payload) {
    try {
        const data = JSON.parse(payload);
        presetsData = data.presets || [];
        activePreset = data.active_preset || null;
        defaultPreset = data.default_preset || null;
        buildPresetsUI();
    } catch (e) {
        console.error('Error parsing presets status:', e);
    }
}

function buildPresetsUI() {
    const container = document.getElementById('presetsList');
    if (!container) return;

    if (presetsData.length === 0) {
        container.innerHTML = '<p><em>No presets saved</em></p>';
        return;
    }

    let html = '';
    presetsData.forEach(preset => {
        const isActive = preset.name === activePreset;
        const isDefault = preset.name === defaultPreset;
        const classes = ['preset-card'];
        if (isActive) classes.push('preset-active');
        if (isDefault) classes.push('preset-default');

        const defaultStar = isDefault ? '<span class="preset-default-badge">DEFAULT</span>' : '';
        const activeDot = isActive ? '<span class="preset-active-dot"></span>' : '';

        // Info line
        const infoParts = [];
        if (preset.shader) infoParts.push(preset.shader);
        if (preset.launcher_action) {
            const a = preset.launcher_action;
            infoParts.push(`${a.type}: ${a.file}`);
        }
        if (preset.gamepad_combo && preset.gamepad_combo.length > 0) {
            infoParts.push(preset.gamepad_combo.map(b => b.replace('BTN_', '')).join('+'));
        }
        const infoText = infoParts.length > 0 ? infoParts.join(' | ') : 'No shader set';

        html += `<div class="${classes.join(' ')}">
            <div class="preset-header">
                <div class="preset-name">${activeDot}${preset.name}${defaultStar}</div>
                <div class="preset-actions">
                    <button onclick="activatePreset('${escapeAttr(preset.name)}')" class="preset-btn">Activate</button>
                    <button onclick="toggleDefaultPreset('${escapeAttr(preset.name)}')" class="preset-btn">${isDefault ? 'Unset Default' : 'Set Default'}</button>
                    <button onclick="startEditPreset('${escapeAttr(preset.name)}')" class="preset-btn">Edit</button>
                    <button onclick="exportPresetJson('${escapeAttr(preset.name)}')" class="preset-btn">Export</button>
                    <button onclick="deletePreset('${escapeAttr(preset.name)}')" class="preset-btn preset-btn-danger">Delete</button>
                </div>
            </div>
            <div class="preset-info">${infoText}</div>
            <div id="preset-edit-${escapeAttr(preset.name)}" class="preset-edit-area" style="display:none;"></div>
        </div>`;
    });

    container.innerHTML = html;
}

function escapeAttr(str) {
    return str.replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function saveCurrentAsPreset() {
    const name = prompt('Preset name:');
    if (!name || !name.trim()) return;

    // Get current shader
    const shader = typeof currentAnimation !== 'undefined' ? currentAnimation : null;

    // Get current uniform values
    const uniforms = {};
    if (typeof currentUniformValues !== 'undefined' && typeof animationsData !== 'undefined' && shader) {
        const animData = animationsData[shader];
        if (animData && animData.uniforms) {
            for (const uniformDef of animData.uniforms) {
                const uName = uniformDef.name;
                const uType = uniformDef.type;
                if (uName in currentUniformValues) {
                    uniforms[uName] = {
                        display: 'both',
                        type: uType,
                        value: currentUniformValues[uName]
                    };
                }
            }
        }
    }

    // Get current teensy values
    const teensy = {};
    if (typeof teensyValues !== 'undefined') {
        for (const [param, data] of Object.entries(teensyValues)) {
            if (data && data.value !== undefined) {
                teensy[param] = data.value;
            }
        }
    }

    // Get current ESP hue overrides
    const esp = {};
    if (typeof espHueValues !== 'undefined') {
        esp.hueF = espHueValues.hueF !== undefined ? espHueValues.hueF : -1;
        esp.hueB = espHueValues.hueB !== undefined ? espHueValues.hueB : -1;
    }

    const preset = {
        name: name.trim(),
        shader: shader,
        uniforms: uniforms,
        teensy: teensy,
        esp: esp,
        launcher_action: null,
        gamepad_combo: null
    };

    // Check if updating an existing preset — keep its launcher_action and gamepad_combo
    const existing = presetsData.find(p => p.name === name.trim());
    if (existing) {
        preset.launcher_action = existing.launcher_action;
        preset.gamepad_combo = existing.gamepad_combo;
    }

    sendCommand('protogen/fins/launcher/preset/save', JSON.stringify(preset));
}

function activatePreset(name) {
    sendCommand('protogen/fins/launcher/preset/activate', JSON.stringify({ name: name }));
}

function deletePreset(name) {
    if (!confirm(`Delete preset "${name}"?`)) return;
    sendCommand('protogen/fins/launcher/preset/delete', JSON.stringify({ name: name }));
}

function toggleDefaultPreset(name) {
    const newDefault = (name === defaultPreset) ? null : name;
    sendCommand('protogen/fins/launcher/preset/set_default', JSON.stringify({ name: newDefault }));
}

// Edit preset (launcher action + gamepad combo)
function startEditPreset(name) {
    const editArea = document.getElementById(`preset-edit-${escapeAttr(name)}`);
    if (!editArea) return;

    // Toggle visibility
    if (editArea.style.display !== 'none') {
        editArea.style.display = 'none';
        editingPreset = null;
        return;
    }

    editingPreset = name;
    const preset = presetsData.find(p => p.name === name);
    if (!preset) return;

    // Build edit form
    const action = preset.launcher_action || {};
    const actionType = action.type || '';
    const actionFile = action.file || '';
    const combo = preset.gamepad_combo || [];

    // Available buttons for combos
    const comboButtons = [
        'BTN_SOUTH', 'BTN_EAST', 'BTN_WEST', 'BTN_NORTH',
        'BTN_TL', 'BTN_TR', 'ABS_Z', 'ABS_RZ',
        'DPAD_UP', 'DPAD_DOWN', 'DPAD_LEFT', 'DPAD_RIGHT',
        'BTN_SELECT', 'BTN_START'
    ];
    const buttonLabels = {
        BTN_SOUTH: 'A/Cross', BTN_EAST: 'B/Circle', BTN_WEST: 'X/Square', BTN_NORTH: 'Y/Triangle',
        BTN_TL: 'LB/L1', BTN_TR: 'RB/R1', ABS_Z: 'LT/L2', ABS_RZ: 'RT/R2',
        DPAD_UP: 'D-Up', DPAD_DOWN: 'D-Down', DPAD_LEFT: 'D-Left', DPAD_RIGHT: 'D-Right',
        BTN_SELECT: 'Select', BTN_START: 'Start'
    };

    // Build file options for launcher action
    const videoOpts = (typeof videoFiles !== 'undefined' ? videoFiles : []).map(f =>
        `<option value="${f}" ${actionType === 'video' && actionFile === f ? 'selected' : ''}>${f}</option>`
    ).join('');
    const execOpts = (typeof execFiles !== 'undefined' ? execFiles : []).map(f =>
        `<option value="${f}" ${actionType === 'exec' && actionFile === f ? 'selected' : ''}>${f}</option>`
    ).join('');
    const audioOpts = (typeof audioFiles !== 'undefined' ? audioFiles : []).map(f =>
        `<option value="${f}" ${actionType === 'audio' && actionFile === f ? 'selected' : ''}>${f}</option>`
    ).join('');

    let html = `
        <div class="preset-edit-section">
            <label>Launcher Action</label>
            <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                <select id="edit-action-type-${escapeAttr(name)}" onchange="updateActionFileSelect('${escapeAttr(name)}')" style="min-width: 100px;">
                    <option value="" ${!actionType ? 'selected' : ''}>None</option>
                    <option value="video" ${actionType === 'video' ? 'selected' : ''}>Video</option>
                    <option value="exec" ${actionType === 'exec' ? 'selected' : ''}>Exec</option>
                    <option value="audio" ${actionType === 'audio' ? 'selected' : ''}>Audio</option>
                </select>
                <select id="edit-action-file-video-${escapeAttr(name)}" style="display:${actionType === 'video' ? 'block' : 'none'}; flex: 1; min-width: 120px;">
                    <option value="">Select file...</option>${videoOpts}
                </select>
                <select id="edit-action-file-exec-${escapeAttr(name)}" style="display:${actionType === 'exec' ? 'block' : 'none'}; flex: 1; min-width: 120px;">
                    <option value="">Select file...</option>${execOpts}
                </select>
                <select id="edit-action-file-audio-${escapeAttr(name)}" style="display:${actionType === 'audio' ? 'block' : 'none'}; flex: 1; min-width: 120px;">
                    <option value="">Select file...</option>${audioOpts}
                </select>
            </div>
        </div>
        <div class="preset-edit-section">
            <label>Gamepad Combo (hold all simultaneously)</label>
            <div class="preset-combo-grid">
                ${comboButtons.map(btn => `
                    <label class="preset-combo-btn">
                        <input type="checkbox" value="${btn}" ${combo.includes(btn) ? 'checked' : ''}>
                        <span>${buttonLabels[btn]}</span>
                    </label>
                `).join('')}
            </div>
        </div>
        <div class="button-group" style="margin-top: 10px;">
            <button onclick="savePresetEdit('${escapeAttr(name)}')">Save Changes</button>
            <button onclick="resavePresetState('${escapeAttr(name)}')">Re-capture Current State</button>
        </div>
    `;

    editArea.innerHTML = html;
    editArea.style.display = 'block';
}

function updateActionFileSelect(name) {
    const typeSelect = document.getElementById(`edit-action-type-${escapeAttr(name)}`);
    const type = typeSelect ? typeSelect.value : '';

    ['video', 'exec', 'audio'].forEach(t => {
        const el = document.getElementById(`edit-action-file-${t}-${escapeAttr(name)}`);
        if (el) el.style.display = (t === type) ? 'block' : 'none';
    });
}

function savePresetEdit(name) {
    const preset = presetsData.find(p => p.name === name);
    if (!preset) return;

    // Read launcher action
    const typeSelect = document.getElementById(`edit-action-type-${escapeAttr(name)}`);
    const actionType = typeSelect ? typeSelect.value : '';

    let launcherAction = null;
    if (actionType) {
        const fileSelect = document.getElementById(`edit-action-file-${actionType}-${escapeAttr(name)}`);
        const file = fileSelect ? fileSelect.value : '';
        if (file) {
            launcherAction = { type: actionType, file: file };
        }
    }

    // Read gamepad combo
    const editArea = document.getElementById(`preset-edit-${escapeAttr(name)}`);
    const checkboxes = editArea ? editArea.querySelectorAll('.preset-combo-grid input[type="checkbox"]:checked') : [];
    const gamepadCombo = Array.from(checkboxes).map(cb => cb.value);

    // Update preset
    const updated = Object.assign({}, preset, {
        launcher_action: launcherAction,
        gamepad_combo: gamepadCombo.length > 0 ? gamepadCombo : null
    });

    sendCommand('protogen/fins/launcher/preset/save', JSON.stringify(updated));
    editArea.style.display = 'none';
    editingPreset = null;
}

function resavePresetState(name) {
    const preset = presetsData.find(p => p.name === name);
    if (!preset) return;

    // Re-capture current state but keep launcher_action and gamepad_combo
    const shader = typeof currentAnimation !== 'undefined' ? currentAnimation : preset.shader;

    const uniforms = {};
    if (typeof currentUniformValues !== 'undefined' && typeof animationsData !== 'undefined' && shader) {
        const animData = animationsData[shader];
        if (animData && animData.uniforms) {
            for (const uniformDef of animData.uniforms) {
                const uName = uniformDef.name;
                const uType = uniformDef.type;
                if (uName in currentUniformValues) {
                    uniforms[uName] = {
                        display: 'both',
                        type: uType,
                        value: currentUniformValues[uName]
                    };
                }
            }
        }
    }

    const teensy = {};
    if (typeof teensyValues !== 'undefined') {
        for (const [param, data] of Object.entries(teensyValues)) {
            if (data && data.value !== undefined) {
                teensy[param] = data.value;
            }
        }
    }

    const esp = {};
    if (typeof espHueValues !== 'undefined') {
        esp.hueF = espHueValues.hueF !== undefined ? espHueValues.hueF : -1;
        esp.hueB = espHueValues.hueB !== undefined ? espHueValues.hueB : -1;
    }

    const updated = Object.assign({}, preset, {
        shader: shader,
        uniforms: uniforms,
        teensy: teensy,
        esp: esp
    });

    sendCommand('protogen/fins/launcher/preset/save', JSON.stringify(updated));
}

function exportPresetJson(name) {
    const preset = presetsData.find(p => p.name === name);
    if (!preset) return;
    const blob = new Blob([JSON.stringify(preset, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name.replace(/[^a-zA-Z0-9_-]/g, '_') + '.json';
    a.click();
    URL.revokeObjectURL(url);
}

function importPresetJson() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (ev) => {
            try {
                const preset = JSON.parse(ev.target.result);
                if (!preset.name) {
                    alert('Invalid preset: missing name');
                    return;
                }
                const existing = presetsData.find(p => p.name === preset.name);
                if (existing && !confirm(`Preset "${preset.name}" already exists. Overwrite?`)) return;
                sendCommand('protogen/fins/launcher/preset/save', JSON.stringify(preset));
            } catch (err) {
                alert('Failed to parse JSON: ' + err.message);
            }
        };
        reader.readAsText(file);
    };
    input.click();
}
