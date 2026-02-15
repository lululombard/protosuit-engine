// SystemBridge UI handlers — system metrics, fan curve, throttle temp, power controls

// Hardware-fixed PWM levels for each Pi fan trip point (baked into device tree)
const PI_FAN_PWM = [29, 49, 69, 98];

// Current fan curve state (kept in sync with MQTT)
let piFanCurve = null;

function handleSystemMetrics(payload) {
    try {
        const data = JSON.parse(payload);

        // CPU
        const cpuEl = document.getElementById('sysCpu');
        if (cpuEl && data.cpu_percent !== undefined) {
            cpuEl.textContent = `${data.cpu_percent.toFixed(1)}%`;
            cpuEl.style.color = data.cpu_percent > 90 ? '#ff6b6b' : data.cpu_percent > 70 ? '#ffd93d' : '#51cf66';
        }

        // Memory
        const memEl = document.getElementById('sysMem');
        if (memEl && data.memory_percent !== undefined) {
            let memText = `${data.memory_percent.toFixed(1)}%`;
            if (data.memory_used_gb !== undefined && data.memory_total_gb !== undefined) {
                memText += ` (${data.memory_used_gb} / ${data.memory_total_gb} GB)`;
            }
            memEl.textContent = memText;
            memEl.style.color = data.memory_percent > 90 ? '#ff6b6b' : data.memory_percent > 70 ? '#ffd93d' : '#51cf66';
        }

        // Disk
        const diskEl = document.getElementById('sysDisk');
        if (diskEl && data.disk_percent !== undefined) {
            let diskText = `${data.disk_percent.toFixed(1)}%`;
            if (data.disk_free_gb !== undefined && data.disk_total_gb !== undefined) {
                diskText += ` (${data.disk_free_gb} / ${data.disk_total_gb} GB free)`;
            }
            diskEl.textContent = diskText;
            diskEl.style.color = data.disk_percent > 90 ? '#ff6b6b' : data.disk_percent > 80 ? '#ffd93d' : '#51cf66';
        }

        // Temperature
        const tempEl = document.getElementById('sysTemp');
        if (tempEl && data.temperature !== undefined) {
            tempEl.textContent = `${data.temperature.toFixed(1)}°C`;
            tempEl.style.color = data.temperature > 80 ? '#ff6b6b' : data.temperature > 65 ? '#ffd93d' : '#51cf66';
        }

        // CPU frequency (actual / target)
        const freqEl = document.getElementById('sysFreq');
        if (freqEl && data.cpu_freq_mhz !== undefined) {
            const target = data.cpu_freq_target_mhz;
            freqEl.textContent = target ? `${data.cpu_freq_mhz} / ${target} MHz` : `${data.cpu_freq_mhz} MHz`;
        }

        // Fan
        const fanEl = document.getElementById('sysFan');
        if (fanEl && data.fan_rpm !== undefined) {
            fanEl.textContent = `${data.fan_rpm} RPM (${data.fan_percent}%)`;
        }

        // Uptime
        const uptimeEl = document.getElementById('sysUptime');
        if (uptimeEl && data.uptime_seconds !== undefined) {
            uptimeEl.textContent = formatUptime(data.uptime_seconds);
        }

        // Throttle
        const throttleEl = document.getElementById('sysThrottle');
        if (throttleEl && data.throttle_flags) {
            const flags = data.throttle_flags;
            const active = [];
            if (flags.under_voltage_now) active.push('Under-voltage');
            if (flags.freq_capped_now) active.push('Freq capped');
            if (flags.throttled_now) active.push('Throttled');
            if (flags.soft_temp_limit_now) active.push('Temp limit');

            if (active.length > 0) {
                throttleEl.textContent = active.join(', ');
                throttleEl.style.color = '#ff6b6b';
            } else {
                const past = [];
                if (flags.under_voltage_occurred) past.push('Under-voltage');
                if (flags.freq_capped_occurred) past.push('Freq capped');
                if (flags.throttled_occurred) past.push('Throttled');
                if (flags.soft_temp_limit_occurred) past.push('Temp limit');

                if (past.length > 0) {
                    throttleEl.textContent = `OK (past: ${past.join(', ')})`;
                    throttleEl.style.color = '#ffd93d';
                } else {
                    throttleEl.textContent = 'None';
                    throttleEl.style.color = '#51cf66';
                }
            }
        }
    } catch (e) {
        console.error('Error parsing system metrics:', e);
    }
}

function handleSystemFanCurve(payload) {
    try {
        piFanCurve = JSON.parse(payload);
        populatePiFanCurveTable();
    } catch (e) {
        console.error('Error parsing fan curve:', e);
    }
}

function populatePiFanCurveTable() {
    const tbody = document.querySelector('#piFanCurveTable tbody');
    if (!tbody || !piFanCurve) return;

    tbody.innerHTML = '';
    const keys = ['trip_1', 'trip_2', 'trip_3', 'trip_4'];
    keys.forEach((key, index) => {
        const temp = piFanCurve[key];
        const fanPct = PI_FAN_PWM[index];
        const row = document.createElement('tr');
        row.style.marginBottom = '8px';
        row.innerHTML = `
            <td style="padding: 4px 0;">
                <input type="number" value="${temp}" data-key="${key}"
                       style="width: 70px; padding: 4px; font-size: 14px;"
                       min="30" max="100" step="0.5"
                       onchange="updatePiFanCurvePoint('${key}', this.value)">
            </td>
            <td style="display: flex; align-items: center; gap: 10px; padding: 4px 0;">
                <input type="range" min="0" max="100" value="${fanPct}"
                       style="width: 150px; height: 20px; opacity: 0.5;"
                       disabled>
                <span style="width: 45px; font-size: 14px;">${fanPct}%</span>
            </td>
        `;
        tbody.appendChild(row);
    });
}

function updatePiFanCurvePoint(key, value) {
    if (piFanCurve) {
        piFanCurve[key] = parseFloat(value);
    }
}

function handleSystemThrottleTemp(payload) {
    try {
        const data = JSON.parse(payload);
        const el = document.getElementById('throttleTempInput');
        if (el && data.temp !== undefined) {
            el.value = data.temp;
        }
    } catch (e) {
        console.error('Error parsing throttle temp:', e);
    }
}

function formatUptime(seconds) {
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (d > 0) return `${d}d ${h}h ${m}m`;
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
}

// Toggle collapsible sections
function togglePiFanCurve() {
    const editor = document.getElementById('piFanCurveEditor');
    const icon = document.getElementById('piFanCurveToggleIcon');
    if (editor) {
        const hidden = editor.style.display === 'none';
        editor.style.display = hidden ? 'block' : 'none';
        if (icon) icon.textContent = hidden ? '▼' : '▶';
    }
}

function toggleThrottleTemp() {
    const editor = document.getElementById('throttleTempEditor');
    const icon = document.getElementById('throttleTempToggleIcon');
    if (editor) {
        const hidden = editor.style.display === 'none';
        editor.style.display = hidden ? 'block' : 'none';
        if (icon) icon.textContent = hidden ? '▼' : '▶';
    }
}

// Save actions
function savePiFanCurve() {
    if (!piFanCurve) return;
    sendCommand('protogen/fins/systembridge/fan_curve/set', JSON.stringify(piFanCurve));
}

function resetPiFanCurve() {
    const defaults = { trip_1: 50, trip_2: 60, trip_3: 67.5, trip_4: 75 };
    sendCommand('protogen/fins/systembridge/fan_curve/set', JSON.stringify(defaults));
}

function saveThrottleTemp() {
    const temp = parseInt(document.getElementById('throttleTempInput').value);
    sendCommand('protogen/fins/systembridge/throttle_temp/set', JSON.stringify({ temp }));
}

// Power controls with confirmation
function systemReboot() {
    if (confirm('Reboot the system?')) {
        sendCommand('protogen/fins/systembridge/power/reboot', '');
    }
}

function systemShutdown() {
    if (confirm('Shut down the system? You will need physical access to power it back on.')) {
        sendCommand('protogen/fins/systembridge/power/shutdown', '');
    }
}
