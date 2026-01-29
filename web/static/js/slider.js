// Slider Module - Reusable slider components with physics support

class Slider {
    constructor(name, min, max, step, value, type = 'float', callbacks = {}) {
        this.name = name;
        this.min = min;
        this.max = max;
        this.step = step;
        this.value = value;
        this.type = type;
        this.callbacks = callbacks;
        this.element = null;
        this.valueDisplay = null;
    }

    generateHTML(wrapper = true) {
        const valueDisplayId = `value_${this.name}`;
        const sliderId = `uniform_${this.name}`;

        // Use custom oninput function if provided, otherwise use default
        const oninputFunc = this.callbacks.oninputFunc || `setUniformRealtimeSmooth('${this.name}', '${this.type}')`;
        const onmousedownFunc = this.callbacks.onmousedownFunc || `sliderStart('${this.name}')`;
        const onmouseupFunc = this.callbacks.onmouseupFunc || `sliderEnd('${this.name}')`;

        // Format value based on type
        const displayValue = this.type === 'int' ? Math.round(this.value).toString() : this.value.toFixed(3);

        const sliderHTML = `
            <input type="range" id="${sliderId}"
                min="${this.min}" max="${this.max}" step="${this.step}" value="${this.value}"
                style="width: 80%; vertical-align: middle;"
                oninput="${oninputFunc}"
                onmousedown="${onmousedownFunc}"
                onmouseup="${onmouseupFunc}"
                ontouchstart="${onmousedownFunc}"
                ontouchend="${onmouseupFunc}">
            <span id="${valueDisplayId}" class="value-display" style="margin-left: 10px;">${displayValue}</span>
        `;

        if (wrapper) {
            return `<div style="margin: 5px 0;">${sliderHTML}</div>`;
        } else {
            return sliderHTML;
        }
    }

    attach() {
        this.element = document.getElementById(`uniform_${this.name}`);
        this.valueDisplay = document.getElementById(`value_${this.name}`);

        if (this.element && this.valueDisplay) {
            this.element.addEventListener('input', (e) => {
                this.value = parseFloat(e.target.value);
                this.valueDisplay.textContent = this.value.toFixed(3);
                if (this.callbacks.onInput) {
                    this.callbacks.onInput(this.value);
                }
            });
        }
    }

    updateValue(newValue) {
        this.value = newValue;
        if (this.element) {
            this.element.value = newValue;
        }
        if (this.valueDisplay) {
            this.valueDisplay.textContent = newValue.toFixed(3);
        }
    }
}

class Vec3Slider {
    constructor(name, min, max, step, values, callbacks = {}) {
        this.name = name;
        this.min = min;
        this.max = max;
        this.step = step;
        this.values = values; // [r, g, b]
        this.callbacks = callbacks;
        this.colorPreview = null;

        // Create individual Slider instances for each component
        this.components = ['r', 'g', 'b'];
        this.componentSliders = {};

        this.components.forEach((comp, index) => {
            this.componentSliders[comp] = new Slider(
                `${this.name}_${comp}`,
                min,
                max,
                step,
                values[index],
                'float',
                {
                    // Custom HTML function calls for vec3 components
                    oninputFunc: `setVec3UniformRealtimeSmooth('${this.name}')`,
                    onmousedownFunc: `sliderStart('${this.name}_${comp}')`,
                    onmouseupFunc: `sliderEnd('${this.name}_${comp}')`,
                    // JavaScript callbacks for internal handling
                    onInput: (value) => {
                        this.values[index] = value;
                        this.updateColorPreview();
                        if (this.callbacks.onInput) {
                            this.callbacks.onInput(this.values);
                        }
                    },
                    onStart: () => {
                        if (this.callbacks.onStart) {
                            this.callbacks.onStart(comp);
                        }
                    },
                    onEnd: () => {
                        if (this.callbacks.onEnd) {
                            this.callbacks.onEnd(comp);
                        }
                    }
                }
            );
        });
    }

    generateHTML() {
        let html = '';

        // Generate HTML for each component using the individual sliders
        this.components.forEach((comp) => {
            const slider = this.componentSliders[comp];
            const sliderHTML = slider.generateHTML(false); // No wrapper div

            // Wrap in label with component name and proper styling for vec3
            html += `
                <div style="margin: 5px 0;">
                    <label>${comp.toUpperCase()}:
                        ${sliderHTML.replace('width: 80%', 'width: 60%')}
                    </label>
                </div>
            `;
        });

        // Add color preview
        html += this.generateColorPreview();
        return html;
    }

    generateColorPreview() {
        const r = Math.round(this.values[0] * 255);
        const g = Math.round(this.values[1] * 255);
        const b = Math.round(this.values[2] * 255);

        return `
            <div style="margin-top: 5px; padding: 10px; background: rgb(${r}, ${g}, ${b}); border: 1px solid #ccc; border-radius: 3px;"
                 id="color_preview_${this.name}"></div>
        `;
    }

    attach() {
        // Attach each component slider
        this.components.forEach((comp) => {
            this.componentSliders[comp].attach();
        });

        this.colorPreview = document.getElementById(`color_preview_${this.name}`);
    }

    updateColorPreview() {
        if (this.colorPreview) {
            const r = Math.round(this.values[0] * 255);
            const g = Math.round(this.values[1] * 255);
            const b = Math.round(this.values[2] * 255);
            this.colorPreview.style.background = `rgb(${r}, ${g}, ${b})`;
        }
    }

    updateValues(newValues) {
        this.values = newValues;

        this.components.forEach((comp, index) => {
            this.componentSliders[comp].updateValue(newValues[index]);
        });

        this.updateColorPreview();
    }
}

// Helper function to create Vec3 sliders
function createVec3Sliders(name, min, max, step, values, callbacks = {}) {
    return new Vec3Slider(name, min, max, step, values, callbacks);
}

// Export for global access
window.Slider = Slider;
window.Vec3Slider = Vec3Slider;
window.createVec3Sliders = createVec3Sliders;
