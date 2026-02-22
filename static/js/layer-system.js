/* LAYER SYSTEM — DT position map, palette generation, layer switching, legend */

function buildDtPositionMap() {
    dtPositionMap = {};
    if (!complianceData || !complianceData.position_groups) return;
    complianceData.position_groups.forEach(pg => {
        if (pg.product_id && pg.groups) {
            dtPositionMap[pg.product_id] = pg.groups;
        }
    });
}

function buildDtPaletteForLevel(levelName) {
    if (DT_KNOWN_PALETTES[levelName]) return DT_KNOWN_PALETTES[levelName];
    const groups = new Set();
    Object.values(dtPositionMap).forEach(g => {
        if (g && g[levelName]) groups.add(g[levelName]);
    });
    const palette = {};
    [...groups].sort().forEach((g, i) => {
        palette[g] = DT_AUTO_COLORS[i % DT_AUTO_COLORS.length];
    });
    return palette;
}

function setLayer(layer) {
    currentLayer = layer;
    document.querySelectorAll('.layer-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.layer === layer);
    });
    renderPlanogram();
}

function updateLayerSelector() {
    const selector = document.getElementById('layerSelector');
    if (!selector) return;
    selector.querySelectorAll('.dt-btn').forEach(b => b.remove());

    if (!decisionTreeData || !decisionTreeData.levels || decisionTreeData.levels.length === 0) {
        if (currentLayer !== 'products') { currentLayer = 'products'; }
        document.getElementById('dtLegend').innerHTML = '';
        return;
    }
    decisionTreeData.levels.forEach((lvl, i) => {
        const btn = document.createElement('button');
        btn.className = 'layer-btn dt-btn';
        btn.dataset.layer = `dt-${i}`;
        btn.textContent = lvl.name;
        btn.onclick = () => setLayer(`dt-${i}`);
        selector.appendChild(btn);
    });
    const validLayers = ['products', ...decisionTreeData.levels.map((_, i) => `dt-${i}`)];
    if (!validLayers.includes(currentLayer)) { currentLayer = 'products'; }
    selector.querySelectorAll('.layer-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.layer === currentLayer);
    });
}

function renderLayerLegend(levelName, palette) {
    const legendEl = document.getElementById('dtLegend');
    if (!legendEl) return;
    legendEl.innerHTML = '';
    if (!levelName || !palette || Object.keys(palette).length === 0) return;
    Object.entries(palette).forEach(([group, color]) => {
        const item = document.createElement('div');
        item.className = 'legend-item';
        item.innerHTML = `
            <div class="legend-swatch" style="background:${color}"></div>
            <span class="legend-label">${group}</span>
        `;
        legendEl.appendChild(item);
    });
}
