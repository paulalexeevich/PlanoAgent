/* API — Backend communication (fetch, generate equipment, fill products, reset) */

async function fetchPlanogram() {
    showLoading(true);
    try {
        const res = await fetch('/api/planogram');
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
