/* Photo Viewer — Sales-per-meter calculation and color mode switching. */

function calculateSalesPerMeter() {
    PV.salesPerMeter.map = {};
    const artInfo = {};

    PV.photos.forEach(name => {
        const data = PV.photoData[name];
        if (!data) return;
        data.products.forEach(p => {
            const key = p.art;
            if (!artInfo[key]) {
                artInfo[key] = { count: 0, width_cm: p.facing_width_cm || 0, product_id: p.product_id };
            }
            artInfo[key].count++;
            if (!artInfo[key].width_cm && p.facing_width_cm) {
                artInfo[key].width_cm = p.facing_width_cm;
            }
        });
    });

    const values = [];
    Object.entries(artInfo).forEach(([art, info]) => {
        const sd = PV.salesData[art] || PV.salesData[info.product_id];
        if (!sd || !info.width_cm || info.count === 0) return;
        const totalShelfMeters = info.count * info.width_cm / 100;
        const spm = sd.avg_sale_amount / totalShelfMeters;
        const entry = { salesPerMeter: spm, color: '#22c55e' };
        PV.salesPerMeter.map[art] = entry;
        if (info.product_id) PV.salesPerMeter.map[info.product_id] = entry;
        values.push(spm);
    });

    PV.salesPerMeter.avg = values.length > 0
        ? values.reduce((a, b) => a + b, 0) / values.length
        : 0;

    Object.entries(PV.salesPerMeter.map).forEach(([art, data]) => {
        if (data.salesPerMeter >= PV.salesPerMeter.avg * 2) {
            data.color = '#ef4444';
        } else if (data.salesPerMeter <= PV.salesPerMeter.avg / 2) {
            data.color = '#f59e0b';
        } else {
            data.color = '#22c55e';
        }
    });
}

function setColorMode(mode) {
    PV.colorMode = mode;
    document.querySelectorAll('#colorModeToggle button').forEach(b => {
        b.classList.toggle('active', b.getAttribute('data-mode') === mode);
    });
    if (mode === 'salesPerMeter') {
        calculateSalesPerMeter();
    }
    renderAllOverlays();
    renderProductList();
    updateSalesPerMeterLegend();
    applyRealogramColorMode();
}

function applyRealogramColorMode() {
    document.querySelectorAll('.product-block[data-art]').forEach(el => {
        el.querySelectorAll('.spm-tint').forEach(t => t.remove());

        if (PV.colorMode === 'salesPerMeter') {
            const art = el.dataset.art;
            const data = PV.salesPerMeter.map[art];
            const color = data ? data.color : '#888888';
            const tint = document.createElement('div');
            tint.className = 'spm-tint';
            tint.style.background = color;
            tint.style.opacity = '0.35';
            tint.style.border = `2px solid ${color}`;
            tint.style.boxSizing = 'border-box';
            el.appendChild(tint);
        }
    });
}

function updateSalesPerMeterLegend() {
    let existing = document.getElementById('spmLegend');
    if (PV.colorMode !== 'salesPerMeter') {
        if (existing) existing.remove();
        return;
    }
    if (!existing) {
        existing = document.createElement('div');
        existing.id = 'spmLegend';
        existing.className = 'spm-legend';
        document.querySelector('.toolbar').appendChild(existing);
    }
    const avgFormatted = PV.salesPerMeter.avg.toLocaleString('ru-RU', {maximumFractionDigits: 0});
    existing.innerHTML = `
        <span class="spm-dot" style="background:#ef4444"></span> &gt;2× avg (${avgFormatted} ₽/m)
        <span class="spm-dot" style="background:#22c55e;margin-left:8px"></span> normal
        <span class="spm-dot" style="background:#f59e0b;margin-left:8px"></span> &lt;½ avg
        <span class="spm-dot" style="background:#888;margin-left:8px"></span> no data
    `;
}
