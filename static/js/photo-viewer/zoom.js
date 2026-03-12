/* Photo Viewer — Zoom, scale, and fit-to-window logic. */

function applyScaleToPhoto(name, scale) {
    const img = document.getElementById(`img-${name}`);
    const size = PV.naturalSizes[name];
    if (!img || !size) return;
    const w = Math.round(size.w * scale);
    const h = Math.round(size.h * scale);
    img.style.width = w + 'px';
    img.style.height = h + 'px';
    PV.scales[name] = scale;
}

function scheduleReRenderPlanograms() {
    if (PV.planoRenderTimer) clearTimeout(PV.planoRenderTimer);
    PV.planoRenderTimer = setTimeout(renderAllMiniPlanograms, 120);
}

function zoomAll(delta) {
    if (PV.globalScale === null) PV.globalScale = 0.3;
    PV.globalScale = Math.max(0.05, Math.min(2, PV.globalScale + delta));
    PV.photos.forEach(name => {
        if (document.getElementById(`canvas-${name}`)) {
            applyScaleToPhoto(name, PV.globalScale);
        }
    });
    document.getElementById('zoomLabel').textContent = Math.round(PV.globalScale * 100) + '%';
    scheduleReRenderPlanograms();
}

function zoomFitAll() {
    const grid = document.getElementById('photosGrid');
    const panel = document.getElementById('sidePanel');
    const toolbar = document.querySelector('.toolbar');
    const visiblePhotos = PV.photos.filter(n => document.getElementById(`card-${n}`));
    const count = visiblePhotos.length || 1;

    const panelW = panel.classList.contains('open') ? panel.offsetWidth : 0;
    const totalW = window.innerWidth - panelW - 1;
    const totalH = window.innerHeight - toolbar.offsetHeight;
    const headerH = 26;
    const planoHeaderH = 30;
    const planoFooterH = 28;
    const pad = 16;
    const gaps = (count - 1) * 8;
    const availW = (totalW - pad - gaps) / count;
    const fixedOverhead = pad + headerH + planoHeaderH + planoFooterH;
    const availH = totalH - fixedOverhead;

    let fitScale = 1;
    visiblePhotos.forEach(name => {
        const size = PV.naturalSizes[name];
        if (!size) return;
        const sw = availW / size.w;
        const bay = PV.recog.bayMap[name];
        const bayWidthIn = bay ? bay.width_in : 49.21;
        const bayHeightIn = bay ? bay.height_in : 0;
        const effectiveH = size.h + (bay ? bayHeightIn * size.w / bayWidthIn : 0);
        const sh = availH / effectiveH;
        fitScale = Math.min(fitScale, sw, sh);
    });

    PV.globalScale = Math.max(0.02, fitScale);
    visiblePhotos.forEach(name => applyScaleToPhoto(name, PV.globalScale));
    document.getElementById('zoomLabel').textContent = Math.round(PV.globalScale * 100) + '%';
    scheduleReRenderPlanograms();
}
