/* SETTINGS — Settings overlay, currency formatting, persistence */

const CURRENCIES = {
    USD: { symbol: '$', code: 'USD', name: 'US Dollar',       placement: 'before' },
    EUR: { symbol: '€', code: 'EUR', name: 'Euro',            placement: 'before' },
    GBP: { symbol: '£', code: 'GBP', name: 'British Pound',   placement: 'before' },
    JPY: { symbol: '¥', code: 'JPY', name: 'Japanese Yen',    placement: 'before', decimals: 0 },
    CAD: { symbol: 'C$', code: 'CAD', name: 'Canadian Dollar', placement: 'before' },
    AUD: { symbol: 'A$', code: 'AUD', name: 'Australian Dollar', placement: 'before' },
    CHF: { symbol: 'CHF', code: 'CHF', name: 'Swiss Franc',   placement: 'after' },
    CNY: { symbol: '¥', code: 'CNY', name: 'Chinese Yuan',    placement: 'before' },
    RUB: { symbol: '₽', code: 'RUB', name: 'Russian Ruble',   placement: 'after', decimals: 0 },
    BRL: { symbol: 'R$', code: 'BRL', name: 'Brazilian Real',  placement: 'before' },
    MXN: { symbol: 'MX$', code: 'MXN', name: 'Mexican Peso',  placement: 'before' },
    KRW: { symbol: '₩', code: 'KRW', name: 'South Korean Won', placement: 'before', decimals: 0 },
};

function cFmt(value) {
    const c = CURRENCIES[currency] || CURRENCIES.USD;
    const dec = c.decimals !== undefined ? c.decimals : 2;
    const num = Number(value).toFixed(dec);
    return c.placement === 'after' ? num + ' ' + c.symbol : c.symbol + num;
}

function cSymbol() {
    return (CURRENCIES[currency] || CURRENCIES.USD).symbol;
}

function setCurrency(code) {
    if (!CURRENCIES[code]) return;
    currency = code;
    const sel = document.getElementById('settingsCurrency');
    if (sel) sel.value = code;
    saveSettings();
    if (planogramData) renderAll();
}

function setShowDimensions(val) {
    showDimensions = val;
    document.querySelector('.planogram-container')
        ?.classList.toggle('show-dimensions', showDimensions);
    saveSettings();
}

function setFillMode(mode) {
    fillMode = mode;
    const sel = document.getElementById('fillMode');
    if (sel) sel.value = mode;
    saveSettings();
}

function setDataSource(source) {
    dataSource = source;
    const sel = document.getElementById('dataSource');
    if (sel) sel.value = source;
    saveSettings();
}

function setColorMode(mode) {
    colorMode = mode;
    const sel = document.getElementById('colorMode');
    if (sel) sel.value = mode;
    saveSettings();
    if (planogramData) renderAll();
}

function setDisplayLayer(layer, visible) {
    displayLayers[layer] = visible;
    saveSettings();
    if (planogramData) renderAll();
}

function openSettings() {
    const overlay = document.getElementById('settingsOverlay');
    document.getElementById('settingsUnitIn').classList.toggle('active', !useMetric);
    document.getElementById('settingsUnitCm').classList.toggle('active', useMetric);
    document.getElementById('settingsCurrency').value = currency;
    document.getElementById('fillMode').value = fillMode || 'algorithm';
    document.getElementById('settingsShowDims').checked = showDimensions;
    document.getElementById('dataSource').value = dataSource || 'supabase';
    document.getElementById('colorMode').value = colorMode || 'price_meter';
    document.getElementById('layerProducts').checked = displayLayers.products !== false;
    document.getElementById('layerShelves').checked = displayLayers.shelves === true;
    document.getElementById('layerLabels').checked = displayLayers.labels === true;
    overlay.classList.add('open');
}

function closeSettings() {
    document.getElementById('settingsOverlay').classList.remove('open');
}

function settingsSetUnit(unit) {
    setUnit(unit);
    document.getElementById('settingsUnitIn').classList.toggle('active', !useMetric);
    document.getElementById('settingsUnitCm').classList.toggle('active', useMetric);
    saveSettings();
}

function saveSettings() {
    try {
        localStorage.setItem('planogram_settings', JSON.stringify({
            useMetric,
            currency,
            fillMode,
            showDimensions,
            scale,
            editorScale: EDITOR_SCALE,
            dataSource,
            colorMode,
            displayLayers,
        }));
    } catch (_) { /* localStorage unavailable */ }
}

function loadSettings() {
    try {
        const raw = localStorage.getItem('planogram_settings');
        if (!raw) return;
        const s = JSON.parse(raw);
        if (s.useMetric !== undefined && s.useMetric !== useMetric) {
            useMetric = s.useMetric;
            const uIn = document.getElementById('unitIn');
            const uCm = document.getElementById('unitCm');
            if (uIn) uIn.classList.toggle('active', !useMetric);
            if (uCm) uCm.classList.toggle('active', useMetric);
        }
        if (s.currency && CURRENCIES[s.currency]) {
            currency = s.currency;
        }
        if (s.fillMode) {
            fillMode = s.fillMode;
            const sel = document.getElementById('fillMode');
            if (sel) sel.value = fillMode;
        }
        if (s.showDimensions !== undefined) {
            showDimensions = s.showDimensions;
        }
        if (typeof s.scale === 'number') {
            scale = s.scale;
            const slider = document.getElementById('scaleSlider');
            if (slider) slider.value = scale;
        }
        if (typeof s.editorScale === 'number') {
            EDITOR_SCALE = s.editorScale;
        }
        if (s.dataSource) {
            dataSource = s.dataSource;
        }
        if (s.colorMode) {
            colorMode = s.colorMode;
        }
        if (s.displayLayers) {
            displayLayers = { ...displayLayers, ...s.displayLayers };
        }
        updateScaleLabels();
    } catch (_) { /* localStorage unavailable */ }
}
