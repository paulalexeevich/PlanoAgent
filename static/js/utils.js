/* UTILS — Unit conversion, loading indicators, source tags, error handling */

const IN_TO_CM = 2.54;
const IN_TO_M = 0.0254;

function d(inches) {
    if (!useMetric) return inches;
    return +(inches * IN_TO_CM).toFixed(1);
}
function dUnit() { return useMetric ? 'cm' : 'in'; }
function dFmt(inches) { return d(inches) + (useMetric ? ' cm' : '"'); }
function mFmt(inches) {
    if (!useMetric) return (inches / 12).toFixed(1) + ' ft';
    return (inches * IN_TO_M).toFixed(2) + ' m';
}
function setUnit(unit) {
    const wasMetric = useMetric;
    useMetric = (unit === 'cm');
    document.getElementById('unitIn').classList.toggle('active', !useMetric);
    document.getElementById('unitCm').classList.toggle('active', useMetric);
    const edIn = document.getElementById('edUnitIn');
    const edCm = document.getElementById('edUnitCm');
    if (edIn) edIn.classList.toggle('active', !useMetric);
    if (edCm) edCm.classList.toggle('active', useMetric);
    updateScaleLabels();
    if (typeof syncEditorUnitLabels === 'function') syncEditorUnitLabels();
    if (typeof syncEditorScaleUI === 'function') syncEditorScaleUI();
    if (wasMetric !== useMetric) {
        updateEquipConfigUnits(wasMetric);
        updateEditorToolbarUnits(wasMetric);
    }
    if (planogramData) renderAll();
}

function updateScaleLabels() {
    const u = 'px/' + dUnit();
    document.getElementById('scaleValue').textContent = scale + u;
    const edLabel = document.getElementById('edScaleValue');
    if (edLabel && typeof EDITOR_SCALE !== 'undefined') edLabel.textContent = EDITOR_SCALE + u;
}

function updateEditorToolbarUnits(wasMetric) {
    const factor = useMetric ? IN_TO_CM : (1 / IN_TO_CM);
    convertInputValue('edEqHeight', factor);
    convertInputValue('edEqDepth', factor);
    if (useMetric) {
        setInputConstraints('edEqHeight', 60, 305, 1);
        setInputConstraints('edEqDepth', 15, 122, 1);
    } else {
        setInputConstraints('edEqHeight', 24, 120, 1);
        setInputConstraints('edEqDepth', 6, 48, 1);
    }
}

function updateEquipConfigUnits(wasMetric) {
    const toIn = 1 / IN_TO_CM;
    const toCm = IN_TO_CM;
    const factor = useMetric ? toCm : toIn;
    const u = useMetric ? 'cm' : 'in';

    document.getElementById('labelEqWidth').textContent = `Bay Width (${u})`;
    document.getElementById('labelEqHeight').textContent = `Bay Height (${u})`;
    document.getElementById('labelEqDepth').textContent = `Bay Depth (${u})`;
    document.getElementById('thBayWidth').textContent = `Width (${u})`;
    document.getElementById('thShelfHeights').textContent = `Shelf Heights (${u}, comma-sep)`;

    if (useMetric) {
        setInputConstraints('eqWidth',  30, 305, 1);
        setInputConstraints('eqHeight', 60, 305, 1);
        setInputConstraints('eqDepth',  15, 122, 1);
    } else {
        setInputConstraints('eqWidth',  12, 120, 1);
        setInputConstraints('eqHeight', 24, 120, 1);
        setInputConstraints('eqDepth',   6,  48, 1);
    }

    convertInputValue('eqWidth', factor);
    convertInputValue('eqHeight', factor);
    convertInputValue('eqDepth', factor);

    document.querySelectorAll('#bayConfigTableBody .bay-config-row').forEach(row => {
        const wInput = row.querySelector('.bay-width-input');
        const hInput = row.querySelector('.bay-heights-input');
        if (wInput && wInput.value) {
            wInput.value = +(parseFloat(wInput.value) * factor).toFixed(1);
            if (useMetric) { wInput.min = 30; wInput.max = 305; }
            else           { wInput.min = 12; wInput.max = 120; }
        }
        if (hInput && hInput.value.trim()) {
            hInput.value = hInput.value.split(',')
                .map(v => { const n = parseFloat(v.trim()); return isNaN(n) ? '' : +(n * factor).toFixed(1); })
                .filter(v => v !== '')
                .join(',');
        }
    });

    const examples = useMetric ? '30,36,41,36,30' : '12,14,16,14,12';
    document.getElementById('bayConfigHintExample').textContent = examples;
}

function setInputConstraints(id, min, max, step) {
    const el = document.getElementById(id);
    if (!el) return;
    el.min = min; el.max = max; el.step = step;
}

function convertInputValue(id, factor) {
    const el = document.getElementById(id);
    if (!el || !el.value) return;
    el.value = +(parseFloat(el.value) * factor).toFixed(1);
}

function toInches(val) {
    const n = parseFloat(val);
    if (isNaN(n)) return val;
    return useMetric ? +(n / IN_TO_CM).toFixed(2) : n;
}

function buildProductsMap() {
    productsMap = {};
    if (planogramData && planogramData.products) {
        planogramData.products.forEach(p => { productsMap[p.id] = p; });
    }
}

function showLoading(show, msg) {
    document.getElementById('loadingIndicator').style.display = show ? 'flex' : 'none';
    document.getElementById('planogramView').style.display = show ? 'none' : 'block';
    if (msg) document.getElementById('loadingText').textContent = msg;
}

function setGenEquipLoading(loading) {
    const btn = document.getElementById('genEquipBtn');
    const label = document.getElementById('genEquipLabel');
    const spinner = document.getElementById('genEquipSpinner');
    btn.disabled = loading;
    label.textContent = loading ? 'Generating...' : 'Generate Equipment';
    spinner.style.display = loading ? 'inline-block' : 'none';
}

function setFillLoading(loading) {
    const btn = document.getElementById('fillBtn');
    const label = document.getElementById('fillLabel');
    const spinner = document.getElementById('fillSpinner');
    btn.disabled = loading;
    label.textContent = loading ? 'Filling...' : 'Fill Products';
    spinner.style.display = loading ? 'inline-block' : 'none';
}

function enableFillBtn(enabled) {
    document.getElementById('fillBtn').disabled = !enabled;
}


function showError(msg) {
    const toast = document.getElementById('errorToast');
    document.getElementById('errorMsg').textContent = msg;
    toast.classList.add('active');
    setTimeout(() => toast.classList.remove('active'), 10000);
}

function hideError() {
    document.getElementById('errorToast').classList.remove('active');
}

function formatMs(ms) {
    if (ms == null) return 'N/A';
    if (ms < 1000) return ms + 'ms';
    return (ms / 1000).toFixed(1) + 's';
}

function kpiColorClass(pct) {
    if (pct >= 80) return 's-green';
    if (pct >= 50) return 's-orange';
    return 's-red';
}

function kpiScoreColor(pct) {
    if (pct >= 80) return 'var(--accent-green)';
    if (pct >= 50) return 'var(--accent-orange)';
    return 'var(--accent-red)';
}
