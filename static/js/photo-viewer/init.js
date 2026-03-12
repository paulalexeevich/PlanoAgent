/* Photo Viewer — Initialization: panel, settings, events, data loading.
 * Loaded last — all other modules must be available. */

function openPanelTab(tab) {
    const panel = document.getElementById('sidePanel');
    PV.activeTab = tab;
    panel.classList.add('open');
    switchTab(tab);
    if (tab === 'actions' && !PV.actions.loaded) loadActions();
    else if (tab === 'actions') renderActions();
    setTimeout(zoomFitAll, 280);
}

function closeSidePanel() {
    document.getElementById('sidePanel').classList.remove('open');
    setTimeout(zoomFitAll, 280);
}

function switchTab(tab) {
    PV.activeTab = tab;
    document.querySelectorAll('.side-panel-tab').forEach(b => {
        b.classList.toggle('active', b.getAttribute('data-tab') === tab);
    });
    document.getElementById('tabActions').style.display = tab === 'actions' ? '' : 'none';
    document.getElementById('tabAnalytics').style.display = tab === 'analytics' ? '' : 'none';
}

function toggleSettings(event) {
    event.stopPropagation();
    const menu = document.getElementById('settingsMenu');
    menu.classList.toggle('open');
}

// ── Event listeners ──────────────────────────────────────────────────────

document.getElementById('photosGrid').addEventListener('wheel', (e) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.02 : 0.02;
    zoomAll(delta);
}, { passive: false });

const grid = document.getElementById('photosGrid');

grid.addEventListener('mousedown', (e) => {
    if (e.target.closest('.bbox-product') || e.target.closest('.bbox-shelf')) return;
    PV.drag.active = true;
    PV.drag.startX = e.clientX;
    PV.drag.startY = e.clientY;
    PV.drag.scrollX = grid.scrollLeft;
    PV.drag.scrollY = grid.scrollTop;
    grid.classList.add('dragging');
    e.preventDefault();
});

window.addEventListener('mousemove', (e) => {
    if (!PV.drag.active) return;
    const dx = e.clientX - PV.drag.startX;
    const dy = e.clientY - PV.drag.startY;
    grid.scrollLeft = PV.drag.scrollX - dx;
    grid.scrollTop = PV.drag.scrollY - dy;
});

window.addEventListener('mouseup', () => {
    if (PV.drag.active) {
        PV.drag.active = false;
        grid.classList.remove('dragging');
    }
});

grid.addEventListener('mousedown', (e) => { PV.drag.distance = 0; });
grid.addEventListener('mousemove', () => { if (PV.drag.active) PV.drag.distance++; });
grid.addEventListener('click', (e) => {
    if (PV.drag.distance > 3) return;
    if (e.target.tagName === 'IMG' || e.target.classList.contains('photos-grid') ||
        e.target.classList.contains('photo-card')) {
        clearSelection();
    }
});

document.addEventListener('click', (e) => {
    const menu = document.getElementById('settingsMenu');
    if (menu.classList.contains('open') && !e.target.closest('.settings-dropdown')) {
        menu.classList.remove('open');
    }
});

// ── Initial data loading ─────────────────────────────────────────────────

Promise.all([
    fetch('/api/planogram-facings').then(r => r.json()).catch(err => {
        console.error('[photo_viewer] Failed to load planogram facings:', err);
        return {};
    }),
    fetch('/api/sales-data').then(r => r.json()).catch(err => {
        console.error('[photo_viewer] Failed to load sales data:', err);
        return {};
    }),
]).then(([facings, sales]) => {
    PV.planogramFacings = facings;
    PV.salesData = sales;
    console.log('[photo_viewer] Loaded planogram facings:', Object.keys(facings).length, 'products');
    console.log('[photo_viewer] Sample facings:', Object.keys(facings).slice(0, 5));
}).finally(() => {
    if (PV.photos.length > 0) loadAllPhotos();
});

fetch('/api/actions').then(r => r.json()).then(data => {
    if (data.status === 'success') {
        PV.actions.data = data.actions;
        PV.actions.loaded = true;
        document.getElementById('actionsBadge').textContent = data.actions.length;
        document.getElementById('actionsBadgeTab').textContent = data.actions.length;
    }
}).catch(err => {
    console.error('[photo_viewer] Failed to pre-load actions:', err);
    PV.actions.loaded = false;
});
