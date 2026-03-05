/* API — Backend communication (fetch, generate equipment, fill products, reset) */

async function fetchFullCatalog() {
    try {
        const res = await fetch('/api/products');
        fullCatalog = await res.json();
    } catch (err) {
        console.error('Failed to load full catalog:', err);
    }
}

async function fetchPlanogram() {
    showLoading(true);
    try {
        const mode = typeof APP_MODE !== 'undefined' ? APP_MODE : 'beer';
        const res = await fetch('/api/planogram?mode=' + mode);
        const data = await res.json();
        planogramData = data.planogram;
        summaryData = data.summary;
        decisionTreeData = data.decision_tree || null;
        complianceData = data.compliance || null;
        buildProductsMap();
        renderAll();
        if (planogramData.equipment && planogramData.equipment.bays && planogramData.equipment.bays.length > 0) {
            equipmentGenerated = true;
            enableFillBtn(true);
        }
    } catch (err) {
        console.error('Failed to load planogram:', err);
    }
    showLoading(false);
}

async function generateEquipment() {
    const config = {
        equipment_type: document.getElementById('eqType').value,
        num_bays: document.getElementById('eqBays').value,
        num_shelves: document.getElementById('eqShelves').value,
        bay_width: toInches(document.getElementById('eqWidth').value),
        bay_height: toInches(document.getElementById('eqHeight').value),
        bay_depth: toInches(document.getElementById('eqDepth').value),
        bays_config: collectBaysConfig(),
    };

    setGenEquipLoading(true);
    showLoading(true, 'Generating empty equipment...');
    hideError();
    try {
        const res = await fetch('/api/generate-equipment', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        const data = await res.json();

        if (data.status === 'error') {
            throw new Error(data.error || 'Equipment generation failed');
        }

        planogramData = data.planogram;
        summaryData = data.summary;
        buildProductsMap();
        renderAll();
        equipmentGenerated = true;
        enableFillBtn(true);
    } catch (err) {
        console.error('Equipment generation failed:', err);
        showError('Equipment generation failed: ' + err.message);
    }
    showLoading(false);
    setGenEquipLoading(false);
}

async function fillProducts() {
    if (!equipmentGenerated) return;

    const mode = fillMode || 'algorithm';
    const loadingMsg = mode === 'ai' ? 'Gemini AI is filling products...'
        : mode === 'compare' ? 'Running Algorithm + AI comparison...'
        : mode === 'cross_bay' ? 'Cross-Bay algorithm is filling products...'
        : 'Standard algorithm is filling products...';

    setFillLoading(true);
    showLoading(true, loadingMsg);
    hideError();

    try {
        const payload = { mode };
        if (planogramData && planogramData.equipment) {
            payload.equipment = planogramData.equipment;
        }
        const res = await fetch('/api/fill-products', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (data.status === 'error') {
            throw new Error(data.error || 'Fill products failed');
        }

        if (data.mode === 'compare' && data.comparison) {
            lastCompareData = data.comparison;
            showCompareModal(data.comparison);
            showLoading(false);
            setFillLoading(false);
            return;
        }

        planogramData = data.planogram;
        summaryData = data.summary;
        decisionTreeData = data.decision_tree || null;
        complianceData = data.compliance || null;
        buildProductsMap();
        renderAll();

    } catch (err) {
        console.error('Fill products failed:', err);
        showError('Fill products failed: ' + err.message);
    }
    showLoading(false);
    setFillLoading(false);
}

async function removeProducts() {
    showLoading(true, 'Removing products...');
    hideError();
    try {
        const res = await fetch('/api/remove-products', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        const data = await res.json();
        planogramData = data.planogram;
        summaryData = data.summary;
        decisionTreeData = data.decision_tree || null;
        complianceData = null;
        buildProductsMap();
        renderAll();
        equipmentGenerated = true;
        enableFillBtn(true);
    } catch (err) {
        console.error('Remove products failed:', err);
        showError('Remove products failed: ' + err.message);
    }
    showLoading(false);
}

/* ── Cloud (Supabase) Save / Load ─────────────────────────────── */

async function savePlanogramToCloud() {
    if (!planogramData) {
        showError('No planogram to save');
        return;
    }
    showLoading(true, 'Saving planogram to cloud...');
    hideError();
    try {
        const res = await fetch('/api/planogram/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: planogramData.name || 'Planogram' })
        });
        const data = await res.json();
        if (data.status === 'error') throw new Error(data.error);
        showSaveToast('Planogram saved to cloud');
    } catch (err) {
        console.error('Cloud save failed:', err);
        showError('Cloud save failed: ' + err.message);
    }
    showLoading(false);
}

function showSaveToast(msg) {
    let toast = document.getElementById('saveToast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'saveToast';
        toast.className = 'save-toast';
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.classList.add('active');
    setTimeout(() => toast.classList.remove('active'), 3000);
}

async function openCloudBrowser() {
    const overlay = document.getElementById('cloudOverlay');
    overlay.classList.add('open');
    document.getElementById('cloudLoading').style.display = 'block';
    document.getElementById('cloudEmpty').style.display = 'none';
    document.getElementById('cloudList').innerHTML = '';

    try {
        const res = await fetch('/api/planogram/list');
        const data = await res.json();
        const rows = data.planograms || [];
        document.getElementById('cloudLoading').style.display = 'none';

        if (rows.length === 0) {
            document.getElementById('cloudEmpty').style.display = 'block';
            return;
        }

        const list = document.getElementById('cloudList');
        rows.forEach(row => {
            const card = document.createElement('div');
            card.className = 'cloud-item';
            const dateStr = new Date(row.updated_at).toLocaleString();
            card.innerHTML = `
                <div class="cloud-item-info">
                    <div class="cloud-item-name">${esc(row.name)}</div>
                    <div class="cloud-item-meta">
                        ${esc(row.category || '')} &middot; ${esc(row.equipment_type || '')}
                        &middot; ${row.num_bays || 0} bays &middot; ${row.num_shelves || 0} shelves
                        &middot; ${row.total_products || 0} SKUs &middot; ${row.total_facings || 0} facings
                    </div>
                    <div class="cloud-item-date">${dateStr}</div>
                </div>
                <div class="cloud-item-actions">
                    <button class="btn btn-primary btn-sm" onclick="loadFromCloud(${row.id})">Load</button>
                    <button class="btn btn-danger btn-sm" onclick="deleteFromCloud(${row.id}, this)">Delete</button>
                </div>
            `;
            list.appendChild(card);
        });
    } catch (err) {
        document.getElementById('cloudLoading').textContent = 'Failed to load: ' + err.message;
    }
}

function closeCloudBrowser() {
    document.getElementById('cloudOverlay').classList.remove('open');
}

function esc(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

async function loadFromCloud(rowId) {
    closeCloudBrowser();
    showLoading(true, 'Loading planogram from cloud...');
    hideError();
    try {
        const res = await fetch(`/api/planogram/load/${rowId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        const data = await res.json();
        if (data.status === 'error') throw new Error(data.error);

        planogramData = data.planogram;
        summaryData = data.summary;
        decisionTreeData = data.decision_tree || null;
        complianceData = data.compliance || null;
        buildProductsMap();
        renderAll();

        if (planogramData.equipment && planogramData.equipment.bays && planogramData.equipment.bays.length > 0) {
            equipmentGenerated = true;
            enableFillBtn(true);
        }
        showSaveToast('Planogram loaded from cloud');
    } catch (err) {
        console.error('Cloud load failed:', err);
        showError('Cloud load failed: ' + err.message);
    }
    showLoading(false);
}

async function deleteFromCloud(rowId, btn) {
    if (!confirm('Delete this planogram from cloud?')) return;
    try {
        const res = await fetch(`/api/planogram/delete/${rowId}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.status === 'error') throw new Error(data.error);
        const item = btn.closest('.cloud-item');
        if (item) item.remove();
        if (document.querySelectorAll('.cloud-item').length === 0) {
            document.getElementById('cloudEmpty').style.display = 'block';
        }
    } catch (err) {
        showError('Delete failed: ' + err.message);
    }
}

async function loadDemoCsvPlanogram() {
    showLoading(true, 'Loading demo CSV planogram...');
    hideError();
    try {
        const res = await fetch('/api/load-demo-csv', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        const data = await res.json();
        if (data.status === 'error') {
            throw new Error(data.error || 'Demo CSV load failed');
        }
        planogramData = data.planogram;
        summaryData = data.summary;
        decisionTreeData = null;
        complianceData = null;
        buildProductsMap();
        await fetchFullCatalog();
        renderAll();
        equipmentGenerated = true;
        enableFillBtn(true);
    } catch (err) {
        console.error('Demo CSV load failed:', err);
        showError('Demo CSV load failed: ' + err.message);
    }
    showLoading(false);
}
