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
        setSourceTag('rule_based');
        if (planogramData.products && planogramData.products.length > 0) {
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
        setSourceTag('equipment_only');
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

    const mode = document.getElementById('fillMode').value;
    const loadingMsg = mode === 'ai' ? 'Gemini AI is filling products...'
        : mode === 'compare' ? 'Running Algorithm + AI comparison...'
        : 'Algorithm is filling products...';

    setFillLoading(true);
    showLoading(true, loadingMsg);
    hideError();
    document.getElementById('timingTag').textContent = '';

    try {
        const payload = { mode };
        if (planogramData && planogramData.equipment) {
            payload.equipment = planogramData.equipment;
        }
        const t0 = performance.now();
        const res = await fetch('/api/fill-products', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        const elapsed = Math.round(performance.now() - t0);

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
        setSourceTag(data.source || 'gemini_ai');

        const serverMs = data.timings ? data.timings.total_ms : null;
        const timingText = serverMs
            ? `${(serverMs / 1000).toFixed(1)}s`
            : `${(elapsed / 1000).toFixed(1)}s`;
        document.getElementById('timingTag').textContent = timingText;

    } catch (err) {
        console.error('Fill products failed:', err);
        showError('Fill products failed: ' + err.message);
    }
    showLoading(false);
    setFillLoading(false);
}

async function resetDefault() {
    showLoading(true);
    hideError();
    try {
        const res = await fetch('/api/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        const data = await res.json();
        planogramData = data.planogram;
        summaryData = data.summary;
        buildProductsMap();
        renderAll();
        setSourceTag('rule_based');
        equipmentGenerated = true;
        enableFillBtn(true);
    } catch (err) {
        console.error('Reset failed:', err);
    }
    showLoading(false);
}
