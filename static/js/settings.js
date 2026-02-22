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

function openSettings() {
    const overlay = document.getElementById('settingsOverlay');
    document.getElementById('settingsUnitIn').classList.toggle('active', !useMetric);
    document.getElementById('settingsUnitCm').classList.toggle('active', useMetric);
    document.getElementById('settingsCurrency').value = currency;
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
            scale,
            editorScale: EDITOR_SCALE,
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
            document.getElementById('unitIn').classList.toggle('active', !useMetric);
            document.getElementById('unitCm').classList.toggle('active', useMetric);
        }
        if (s.currency && CURRENCIES[s.currency]) {
            currency = s.currency;
        }
        if (typeof s.scale === 'number') {
            scale = s.scale;
            const slider = document.getElementById('scaleSlider');
            if (slider) slider.value = scale;
        }
        if (typeof s.editorScale === 'number') {
            EDITOR_SCALE = s.editorScale;
        }
        updateScaleLabels();
    } catch (_) { /* localStorage unavailable */ }
}
