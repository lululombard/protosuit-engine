// UI Utilities - Logging, status updates, rate monitoring

// MQTT rate tracking (separate up/down counters)
let mqttMessagesUp = 0;   // Outgoing messages
let mqttMessagesDown = 0; // Incoming messages
let mqttRateInterval = null;

function logMessage(message, type = 'info') {
    const log = document.getElementById('messageLog');
    const timestamp = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.textContent = `[${timestamp}] ${message}`;
    log.appendChild(entry);
    log.scrollTop = log.scrollHeight;
}

function clearLog() {
    document.getElementById('messageLog').innerHTML = 'Log cleared...';
}

function startMQTTRateMonitor() {
    mqttRateInterval = setInterval(() => {
        const rateDisplay = document.getElementById('mqttRate');
        rateDisplay.textContent = `MQTT: ↓${mqttMessagesDown}/s ↑${mqttMessagesUp}/s`;

        // Color code based on total rate
        const totalRate = mqttMessagesUp + mqttMessagesDown;
        if (totalRate > 50) {
            rateDisplay.style.color = '#ff6b6b'; // Red for high rate
        } else if (totalRate > 20) {
            rateDisplay.style.color = '#ffd93d'; // Yellow for medium
        } else {
            rateDisplay.style.color = '#4CAF50'; // Green for low
        }

        // Reset counters
        mqttMessagesUp = 0;
        mqttMessagesDown = 0;
    }, 1000);
}

function trackMessageSent() {
    mqttMessagesUp++;
}

function trackMessageReceived() {
    mqttMessagesDown++;
}

function updateConnectionStatus(connected) {
    const statusText = document.getElementById('statusText');
    const connectBtn = document.getElementById('connectBtn');
    const disconnectBtn = document.getElementById('disconnectBtn');

    if (connected) {
        statusText.textContent = 'Connected (MQTT via WebSocket)';
        statusText.style.color = '#51cf66';
        connectBtn.style.display = 'none';
        disconnectBtn.style.display = 'inline-block';
    } else {
        statusText.textContent = 'Disconnected';
        statusText.style.color = '#ff6b6b';
        connectBtn.style.display = 'inline-block';
        disconnectBtn.style.display = 'none';
    }
}

// ESP32/Visor sensor status handlers
function handleEspSensorStatus(payload) {
    try {
        const data = JSON.parse(payload);

        // Update temperature (handle both old 'temp' and new 'temperature' keys)
        const tempEl = document.getElementById('visorTemp');
        const temp = data.temperature !== undefined ? data.temperature : data.temp;
        if (tempEl && temp !== undefined) {
            tempEl.textContent = `${temp.toFixed(1)}°C`;
            // Color code based on temperature
            if (temp > 35) {
                tempEl.style.color = '#ff6b6b'; // Red - hot
            } else if (temp > 30) {
                tempEl.style.color = '#ffd93d'; // Yellow - warm
            } else {
                tempEl.style.color = '#51cf66'; // Green - ok
            }
        }

        // Update humidity (handle both old 'hum' and new 'humidity' keys)
        const humEl = document.getElementById('visorHumidity');
        const hum = data.humidity !== undefined ? data.humidity : data.hum;
        if (humEl && hum !== undefined) {
            humEl.textContent = `${hum.toFixed(0)}%`;
        }

        // Update RPM
        const rpmEl = document.getElementById('visorRpm');
        if (rpmEl && data.rpm !== undefined) {
            rpmEl.textContent = data.rpm.toString();
        }

        // Update fan speed display (without changing slider if user isn't dragging)
        const fanSlider = document.getElementById('fanSlider');
        const fanValue = document.getElementById('fanSpeedValue');
        if (fanSlider && fanValue && data.fan !== undefined) {
            // Only update if slider isn't being dragged
            if (document.activeElement !== fanSlider) {
                fanSlider.value = data.fan;
                fanValue.textContent = data.fan;
            }
        }

        // Update auto mode indicator from sensor status
        if (data.mode !== undefined) {
            const autoCheck = document.getElementById('fanAutoMode');
            if (autoCheck) {
                autoCheck.checked = data.mode === 'auto';
            }
        }
    } catch (e) {
        console.error('Error parsing ESP sensor data:', e);
    }
}

function handleEspAliveStatus(payload) {
    const espStatus = document.getElementById('espStatus');
    if (espStatus) {
        const isAlive = payload === 'true';
        espStatus.textContent = isAlive ? 'Connected' : 'Disconnected';
        espStatus.style.color = isAlive ? '#51cf66' : '#ff6b6b';
    }
}

function updateFanSpeedDisplay(value) {
    const fanValue = document.getElementById('fanSpeedValue');
    if (fanValue) {
        fanValue.textContent = value;
    }
}

function setFanSpeed(value) {
    sendCommand('protogen/visor/esp/set/fan', value.toString(), true);
}

// Fan curve control
let fanCurveConfig = null;

function applyFanCurveToUI() {
    if (!fanCurveConfig) return;

    // Update auto mode checkbox
    const autoCheck = document.getElementById('fanAutoMode');
    if (autoCheck) {
        autoCheck.checked = fanCurveConfig.mode === 'auto';
    }

    // Update fan slider state
    const fanSlider = document.getElementById('fanSlider');
    if (fanSlider) {
        fanSlider.disabled = fanCurveConfig.mode === 'auto';
        fanSlider.style.opacity = fanCurveConfig.mode === 'auto' ? '0.5' : '1';
    }

    // Populate curve tables
    populateCurveTable('tempCurveTable', fanCurveConfig.temperature, 'value');
    populateCurveTable('humCurveTable', fanCurveConfig.humidity, 'value');
}

function handleFanCurveStatus(payload) {
    try {
        fanCurveConfig = JSON.parse(payload);
        applyFanCurveToUI();

    } catch (e) {
        console.error('Error parsing fan curve config:', e);
    }
}

function populateCurveTable(tableId, points, valueKey) {
    const tbody = document.querySelector(`#${tableId} tbody`);
    if (!tbody || !points) return;

    tbody.innerHTML = '';
    points.forEach((point, index) => {
        const row = document.createElement('tr');
        row.style.marginBottom = '8px';
        row.innerHTML = `
            <td style="padding: 4px 0;">
                <input type="number" value="${point[valueKey]}" data-index="${index}" data-key="${valueKey}"
                       style="width: 70px; padding: 4px; font-size: 14px;"
                       onchange="updateCurvePoint('${tableId}', ${index}, '${valueKey}', this.value)">
            </td>
            <td style="display: flex; align-items: center; gap: 10px; padding: 4px 0;">
                <input type="range" min="0" max="100" value="${point.fan}" data-index="${index}"
                       style="width: 150px; height: 20px;"
                       oninput="this.nextElementSibling.textContent=this.value+'%'"
                       onchange="updateCurvePoint('${tableId}', ${index}, 'fan', this.value)">
                <span style="width: 45px; font-size: 14px;">${point.fan}%</span>
            </td>
            <td style="padding: 4px 0;">
                <button onclick="removeCurvePoint('${tableId}', ${index})"
                        style="padding: 4px 8px; font-size: 12px; color: #ff6b6b; background: transparent; border: 1px solid #ff6b6b;">Delete</button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

function updateCurvePoint(tableId, index, key, value) {
    if (!fanCurveConfig) return;
    const isTemp = tableId === 'tempCurveTable';
    const arr = isTemp ? fanCurveConfig.temperature : fanCurveConfig.humidity;
    if (arr && arr[index]) {
        if (key === 'fan') {
            arr[index].fan = parseInt(value);
        } else {
            arr[index].value = parseFloat(value);
        }
    }
}

function setFanMode(isAuto) {
    sendCommand('protogen/visor/esp/set/fanmode', isAuto ? 'auto' : 'manual', true);

    // Update slider state immediately
    const fanSlider = document.getElementById('fanSlider');
    if (fanSlider) {
        fanSlider.disabled = isAuto;
        fanSlider.style.opacity = isAuto ? '0.5' : '1';
    }
}

function toggleFanCurveEditor() {
    const editor = document.getElementById('fanCurveEditor');
    const icon = document.getElementById('fanCurveToggleIcon');
    if (editor) {
        const isHidden = editor.style.display === 'none';
        editor.style.display = isHidden ? 'block' : 'none';
        if (icon) {
            icon.textContent = isHidden ? '▼' : '▶';
        }
    }
}

function saveFanCurve() {
    if (!fanCurveConfig) return;

    // Sort curves by value before saving
    fanCurveConfig.temperature.sort((a, b) => a.value - b.value);
    fanCurveConfig.humidity.sort((a, b) => a.value - b.value);

    sendCommand('protogen/visor/esp/config/fancurve', JSON.stringify(fanCurveConfig), true);
}

function addTempPoint() {
    if (!fanCurveConfig) return;
    fanCurveConfig.temperature.push({ value: 25, fan: 50 });
    populateCurveTable('tempCurveTable', fanCurveConfig.temperature, 'value');
}

function addHumPoint() {
    if (!fanCurveConfig) return;
    fanCurveConfig.humidity.push({ value: 50, fan: 50 });
    populateCurveTable('humCurveTable', fanCurveConfig.humidity, 'value');
}

function removeCurvePoint(tableId, index) {
    if (!fanCurveConfig) return;
    const isTemp = tableId === 'tempCurveTable';
    const arr = isTemp ? fanCurveConfig.temperature : fanCurveConfig.humidity;
    if (arr && arr.length > 2) {  // Keep at least 2 points
        arr.splice(index, 1);
        populateCurveTable(tableId, arr, 'value');
    }
}

function resetFanCurve() {
    const defaultConfig = {
        mode: 'auto',
        temperature: [
            { value: 15, fan: 0 },
            { value: 20, fan: 30 },
            { value: 25, fan: 50 },
            { value: 30, fan: 80 },
            { value: 35, fan: 100 }
        ],
        humidity: [
            { value: 30, fan: 0 },
            { value: 40, fan: 40 },
            { value: 60, fan: 60 },
            { value: 80, fan: 100 }
        ]
    };
    sendCommand('protogen/visor/esp/config/fancurve', JSON.stringify(defaultConfig), true);
}
