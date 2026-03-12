/* Photo Viewer — Actions panel loading, rendering, and filtering. */

function toggleActionsPanel() {
    const panel = document.getElementById('sidePanel');
    if (panel.classList.contains('open') && PV.activeTab === 'actions') {
        closeSidePanel();
    } else {
        openPanelTab('actions');
    }
}

function loadActions() {
    const loadingTimeout = setTimeout(() => {
        if (!PV.actions.loaded) {
            document.getElementById('actionsList').innerHTML =
                `<div class="empty-state">⏱️ Loading is taking longer than expected...<br>
                <button onclick="loadActions()" style="margin-top:12px;padding:8px 16px;border:1px solid #444;background:#2a2a2a;color:#fff;border-radius:6px;cursor:pointer">Retry</button></div>`;
        }
    }, 8000);

    const controller = new AbortController();
    const fetchTimeout = setTimeout(() => controller.abort(), 15000);

    fetch('/api/actions', { signal: controller.signal })
        .then(r => {
            clearTimeout(fetchTimeout);
            if (!r.ok) {
                throw new Error(`HTTP ${r.status}: ${r.statusText}`);
            }
            return r.json();
        })
        .then(data => {
            clearTimeout(loadingTimeout);
            if (data.status === 'success') {
                PV.actions.data = data.actions;
                PV.actions.loaded = true;
                renderActions();
                document.getElementById('actionsBadge').textContent = PV.actions.data.length;
                document.getElementById('actionsBadgeTab').textContent = PV.actions.data.length;
            } else {
                throw new Error(data.error || 'Unknown error');
            }
        })
        .catch(err => {
            clearTimeout(loadingTimeout);
            clearTimeout(fetchTimeout);
            console.error('[photo_viewer] Failed to load actions:', err);
            PV.actions.loaded = false;
            const errMsg = err.name === 'AbortError'
                ? 'Request timed out (>15s). Server might be slow or unavailable.'
                : err.message;
            document.getElementById('actionsList').innerHTML =
                `<div class="empty-state">❌ Failed to load actions<br>
                <span style="color:#888;font-size:11px">${errMsg}</span><br>
                <button onclick="loadActions()" style="margin-top:12px;padding:8px 16px;border:1px solid #444;background:#2a2a2a;color:#fff;border-radius:6px;cursor:pointer">Retry</button></div>`;
        });
}

function setActionFilter(f) {
    PV.actions.filter = f;
    document.querySelectorAll('.actions-filters .filter-btn').forEach(b => {
        b.classList.toggle('active', b.getAttribute('data-apri') === f);
    });
    renderActions();
}

function renderActions() {
    if (!PV.actions.data || !Array.isArray(PV.actions.data)) {
        document.getElementById('actionsList').innerHTML =
            '<div class="empty-state">No actions data available</div>';
        return;
    }

    const filtered = PV.actions.filter === 'all'
        ? PV.actions.data
        : PV.actions.data.filter(a => a.priority === PV.actions.filter);

    const counts = { high: 0, medium: 0, low: 0 };
    let totalSales = 0;
    PV.actions.data.forEach(a => {
        counts[a.priority] = (counts[a.priority] || 0) + 1;
        totalSales += parseFloat(a.avg_sale_amount || 0);
    });

    document.getElementById('actionsSummary').innerHTML = `
        <div class="actions-stat-row">
            <span><strong>${PV.actions.data.length}</strong> actions</span>
            <span>Lost sales: <strong style="color:#f59e0b">${Math.round(totalSales).toLocaleString('ru-RU')} ₽/wk</strong></span>
        </div>
        <div class="actions-stat-row">
            <span class="apri-high">${counts.high} high</span>
            <span class="apri-med">${counts.medium} medium</span>
            <span class="apri-low">${counts.low} low</span>
        </div>
    `;

    if (filtered.length === 0) {
        document.getElementById('actionsList').innerHTML =
            '<div class="empty-state">No actions match this filter</div>';
        return;
    }

    document.getElementById('actionsList').innerHTML = filtered.map((a, i) => {
        const sale = parseFloat(a.avg_sale_amount || 0);
        const priClass = a.priority === 'high' ? 'apri-high' : a.priority === 'medium' ? 'apri-med' : 'apri-low';

        return `
            <div class="action-card ${priClass}" data-action-id="${a.id}">
                <div class="action-rank">${i + 1}</div>
                <div class="action-body">
                    <div class="action-name">${a.product_name || a.tiny_name}</div>
                    <div class="action-lost-sales">
                        ${sale > 0
                            ? `Lost: <strong>${sale.toLocaleString('ru-RU', {maximumFractionDigits:0})} ₽/wk</strong>`
                            : `<span style="color:var(--text-secondary)">No sales data</span>`}
                    </div>
                    <div class="action-meta">
                        ${a.brand ? `<span class="tag-brand">${a.brand}</span>` : ''}
                        <span class="tag-plano">P:${a.planogram_facings}</span>
                        <span class="tag-oos">Out of shelf</span>
                    </div>
                    ${a.category_l1 || a.category_l2 ? `
                    <div class="action-categories">
                        ${a.category_l1 ? `<span class="tag-cat">${a.category_l1}</span>` : ''}
                        ${a.category_l2 && a.category_l2 !== a.category_l1 ? `<span class="tag-cat2">${a.category_l2}</span>` : ''}
                    </div>` : ''}
                    <div class="action-stats">
                        <span>Qty: <strong>${parseFloat(a.avg_sale_qty || 0).toFixed(1)}</strong>/wk</span>
                        <span>Stock: <strong>${parseFloat(a.avg_stock_qty || 0).toFixed(1)}</strong></span>
                        <span>${a.width_cm}×${a.height_cm} cm</span>
                    </div>
                </div>
                <div class="action-priority ${priClass}">${a.priority}</div>
            </div>
        `;
    }).join('');
}
