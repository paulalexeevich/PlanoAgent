/* DASHBOARD — KPI cards, detail panels, assortment upload */

let activeKpi = null;
let customAssortmentList = null;

function togglePanel() {
    document.getElementById('bottomPanel').classList.toggle('collapsed');
}

function renderSummary() {
    if (!summaryData) return;
    renderKpiCards();
    if (activeKpi) renderKpiDetailContent(activeKpi);
}

function renderKpiCards() {
    const s = summaryData;
    if (!s) return;

    const assort = s.assortment || {};
    let assortPct, assortPlaced, assortTotal;

    if (customAssortmentList && customAssortmentList.length > 0) {
        const placedIds = new Set(assort.placed_ids || []);
        assortPlaced = customAssortmentList.filter(sku => placedIds.has(sku)).length;
        assortTotal = customAssortmentList.length;
        assortPct = assortTotal > 0 ? Math.round(assortPlaced / assortTotal * 100 * 10) / 10 : 0;
    } else {
        assortPct = assort.assortment_pct || 0;
        assortPlaced = assort.total_placed || 0;
        assortTotal = assort.total_catalog || 0;
    }

    const assortCard = document.getElementById('kpiAssortment');
    assortCard.className = `s-card clickable ${kpiColorClass(assortPct)}${activeKpi === 'assortment' ? ' active' : ''}`;
    document.getElementById('kpiAssortmentValue').textContent = assortPct + '%';
    document.getElementById('kpiAssortmentSub').textContent = `${assortPlaced} of ${assortTotal} SKUs placed`;

    const avgRevSpace = s.avg_revenue_per_space || 0;
    const revCard = document.getElementById('kpiRevSpace');
    revCard.className = `s-card clickable s-blue${activeKpi === 'revspace' ? ' active' : ''}`;
    document.getElementById('kpiRevSpaceValue').textContent = '$' + avgRevSpace.toFixed(2);
    const totalRev = s.financials ? s.financials.total_revenue_potential : 0;
    document.getElementById('kpiRevSpaceSub').textContent = `$${totalRev.toLocaleString()} total revenue`;

    const fillPct = s.space_utilization ? s.space_utilization.avg_shelf_fill_rate : 0;
    const spaceCard = document.getElementById('kpiSpaceUtil');
    spaceCard.className = `s-card clickable ${kpiColorClass(fillPct)}${activeKpi === 'spaceutil' ? ' active' : ''}`;
    document.getElementById('kpiSpaceUtilValue').textContent = fillPct + '%';
    const usedIn = s.space_utilization ? s.space_utilization.total_space_used_in : 0;
    const availIn = s.space_utilization ? s.space_utilization.total_space_available_in : 0;
    document.getElementById('kpiSpaceUtilSub').textContent = `${usedIn}" of ${availIn}" used`;

    const compPct = complianceData ? complianceData.overall_pct : 0;
    const compCard = document.getElementById('kpiCompliance');
    if (!complianceData) {
        compCard.className = `s-card clickable${activeKpi === 'compliance' ? ' active' : ''}`;
        document.getElementById('kpiComplianceValue').textContent = '--';
        document.getElementById('kpiComplianceSub').textContent = 'Fill products to see compliance';
    } else {
        compCard.className = `s-card clickable ${kpiColorClass(compPct)}${activeKpi === 'compliance' ? ' active' : ''}`;
        document.getElementById('kpiComplianceValue').textContent = compPct + '%';
        const totalBreaks = complianceData.levels.reduce((s, l) => s + l.break_count, 0);
        document.getElementById('kpiComplianceSub').textContent = totalBreaks === 0 ? 'Perfect grouping' : `${totalBreaks} break(s) detected`;
    }
}

function toggleKpiDetail(kpiId) {
    const panel = document.getElementById('kpiDetailPanel');
    if (activeKpi === kpiId) {
        activeKpi = null;
        panel.classList.remove('open');
        panel.innerHTML = '';
        document.querySelectorAll('#bottomPanel .s-card').forEach(c => c.classList.remove('active'));
    } else {
        activeKpi = kpiId;
        panel.classList.add('open');
        renderKpiDetailContent(kpiId);
        document.querySelectorAll('#bottomPanel .s-card').forEach(c => c.classList.remove('active'));
        document.getElementById({
            'assortment': 'kpiAssortment',
            'revspace': 'kpiRevSpace',
            'spaceutil': 'kpiSpaceUtil',
            'compliance': 'kpiCompliance'
        }[kpiId]).classList.add('active');
    }
}

function renderKpiDetailContent(kpiId) {
    const panel = document.getElementById('kpiDetailPanel');
    if (!summaryData) { panel.innerHTML = ''; return; }

    switch(kpiId) {
        case 'assortment': panel.innerHTML = renderAssortmentDetail(); break;
        case 'revspace': panel.innerHTML = renderRevSpaceDetail(); break;
        case 'spaceutil': panel.innerHTML = renderSpaceUtilDetail(); break;
        case 'compliance': panel.innerHTML = renderComplianceDetail(); break;
        default: panel.innerHTML = '';
    }
}

function renderAssortmentDetail() {
    const assort = summaryData.assortment || {};
    const placedIds = new Set(assort.placed_ids || []);

    let html = '<div class="s-section-title">Assortment Tracking</div>';

    html += `<div class="s-upload-row">
        <button class="s-upload-btn" onclick="document.getElementById('assortmentFileInput').click()">
            Upload SKU List
        </button>
        <span class="s-upload-info" id="assortmentUploadInfo">
            ${customAssortmentList ? customAssortmentList.length + ' custom SKUs loaded' : 'Using full catalog (' + (assort.total_catalog || 0) + ' SKUs)'}
        </span>
        ${customAssortmentList ? '<button class="s-upload-btn" onclick="clearAssortmentList()" style="color:var(--accent-red);border-color:var(--accent-red);">Clear</button>' : ''}
    </div>`;

    let items = [];
    if (customAssortmentList && customAssortmentList.length > 0) {
        const allProducts = planogramData ? planogramData.products || [] : [];
        const prodMap = {};
        allProducts.forEach(p => { prodMap[p.id] = p; });
        customAssortmentList.forEach(sku => {
            const p = prodMap[sku];
            items.push({
                id: sku,
                name: p ? p.name : sku,
                brand: p ? p.brand : '—',
                subcategory: p ? p.subcategory : '—',
                placed: placedIds.has(sku)
            });
        });
    } else {
        const allProducts = planogramData ? planogramData.products || [] : [];
        allProducts.forEach(p => {
            items.push({
                id: p.id,
                name: p.name,
                brand: p.brand,
                subcategory: p.subcategory,
                placed: placedIds.has(p.id)
            });
        });
    }

    items.sort((a, b) => (a.placed === b.placed) ? 0 : a.placed ? 1 : -1);

    html += `<table class="s-table">
        <thead><tr>
            <th>Status</th>
            <th>Product</th>
            <th>Brand</th>
            <th>Category</th>
        </tr></thead><tbody>`;

    items.forEach(item => {
        const statusClass = item.placed ? 's-status-good' : 's-status-bad';
        const statusText = item.placed ? 'Placed' : 'Missing';
        html += `<tr>
            <td class="${statusClass}">${statusText}</td>
            <td>${item.name}</td>
            <td>${item.brand}</td>
            <td>${item.subcategory}</td>
        </tr>`;
    });

    html += '</tbody></table>';
    return html;
}

function renderRevSpaceDetail() {
    const skuList = summaryData.sku_space_analysis || [];
    if (skuList.length === 0) {
        return '<div class="s-section-title">Revenue per Space</div><div style="font-size:11px;color:var(--text-secondary);">No products placed yet</div>';
    }

    let html = '<div class="s-section-title">Revenue per Space — Ranked by $/inch</div>';
    html += `<table class="s-table">
        <thead><tr>
            <th class="rank-col">#</th>
            <th>Product</th>
            <th>Brand</th>
            <th class="right">Facings</th>
            <th class="right">Space</th>
            <th class="right">Revenue</th>
            <th class="right">$/inch</th>
        </tr></thead><tbody>`;

    skuList.forEach((sku, i) => {
        const revColor = sku.revenue_per_space >= (summaryData.avg_revenue_per_space || 0) ? 'var(--accent-green)' : 'var(--accent-orange)';
        html += `<tr>
            <td class="rank-col">${i + 1}</td>
            <td>${sku.name}</td>
            <td style="color:var(--text-secondary)">${sku.brand}</td>
            <td class="right mono">${sku.facings}</td>
            <td class="right mono">${sku.space_in.toFixed(1)}"</td>
            <td class="right mono">$${sku.revenue.toFixed(2)}</td>
            <td class="right mono" style="color:${revColor};font-weight:700">$${sku.revenue_per_space.toFixed(2)}</td>
        </tr>`;
    });

    html += '</tbody></table>';
    return html;
}

function renderSpaceUtilDetail() {
    const rates = summaryData.space_utilization ? summaryData.space_utilization.shelf_fill_rates : [];
    if (!planogramData || !planogramData.equipment) {
        return '<div class="s-section-title">Space Utilization by Shelf</div><div style="font-size:11px;color:var(--text-secondary);">No equipment loaded</div>';
    }

    let html = '<div class="s-section-title">Space Utilization by Shelf</div>';
    html += `<table class="s-table">
        <thead><tr>
            <th>Location</th>
            <th>Fill Rate</th>
            <th style="width:50%" class="right"></th>
        </tr></thead><tbody>`;

    planogramData.equipment.bays.forEach((bay, bi) => {
        bay.shelves.forEach((shelf, si) => {
            const idx = bi * bay.shelves.length + si;
            if (idx >= rates.length) return;
            const rate = rates[idx];
            const colorClass = rate >= 80 ? 's-fill-good' : rate >= 50 ? 's-fill-warn' : 's-fill-low';
            const pctColor = kpiScoreColor(rate);
            html += `<tr>
                <td>Bay ${bi + 1} / Shelf ${si + 1}</td>
                <td class="mono" style="color:${pctColor};font-weight:700">${rate}%</td>
                <td class="right">
                    <div class="s-fill-bar">
                        <div class="s-fill-bar-inner ${colorClass}" style="width:${rate}%"></div>
                    </div>
                </td>
            </tr>`;
        });
    });

    html += '</tbody></table>';
    return html;
}

function renderComplianceDetail() {
    if (!complianceData) {
        return '<div class="s-section-title">Decision Tree Compliance</div><div style="font-size:11px;color:var(--text-secondary);">Fill products to see compliance per layer</div>';
    }

    let html = '<div class="s-section-title">Decision Tree Compliance by Layer</div>';

    if (decisionTreeData) {
        html += '<div class="dt-tree-visual" style="margin-bottom:12px">';
        decisionTreeData.levels.forEach((lvl, i) => {
            if (i > 0) html += '<span class="dt-arrow">&#8594;</span>';
            html += `<span class="dt-level"><span class="dt-num">L${i+1}</span> <span class="dt-name">${lvl.name}</span></span>`;
        });
        html += '</div>';
    }

    complianceData.levels.forEach(lvl => {
        const pct = lvl.compliance_pct;
        const colorClass = pct >= 80 ? 's-fill-good' : pct >= 50 ? 's-fill-warn' : 's-fill-low';
        const pctColor = kpiScoreColor(pct);
        html += `<div class="s-metric-row">
            <span class="s-metric-name">${lvl.level_name}</span>
            <div class="s-metric-bar">
                <div class="s-metric-bar-inner ${colorClass}" style="width:${pct}%"></div>
            </div>
            <span class="s-metric-pct" style="color:${pctColor}">${pct}%</span>
            <span class="s-metric-detail">${lvl.break_count} break${lvl.break_count !== 1 ? 's' : ''}</span>
        </div>`;
    });

    const totalBreaks = complianceData.levels.reduce((s, l) => s + l.break_count, 0);
    if (totalBreaks > 0) {
        html += `<div style="font-size:10px;color:var(--accent-orange);margin-top:8px;">${totalBreaks} total grouping break(s) — products interrupt contiguous segments</div>`;
    } else {
        html += `<div style="font-size:10px;color:var(--accent-green);margin-top:8px;">Perfect grouping — no breaks detected at any level</div>`;
    }

    return html;
}

function handleAssortmentUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(e) {
        const text = e.target.result.trim();
        let skuList = [];

        if (file.name.endsWith('.json')) {
            try {
                const parsed = JSON.parse(text);
                if (Array.isArray(parsed)) {
                    skuList = parsed.map(s => String(s).trim()).filter(Boolean);
                } else {
                    showError('JSON must be an array of SKU IDs');
                    return;
                }
            } catch {
                showError('Invalid JSON file');
                return;
            }
        } else {
            skuList = text.split(/[\n,]+/).map(s => s.trim()).filter(Boolean);
        }

        if (skuList.length === 0) {
            showError('No SKUs found in file');
            return;
        }

        customAssortmentList = skuList;
        renderSummary();
        if (activeKpi === 'assortment') renderKpiDetailContent('assortment');
    };
    reader.readAsText(file);
    event.target.value = '';
}

function clearAssortmentList() {
    customAssortmentList = null;
    renderSummary();
    if (activeKpi === 'assortment') renderKpiDetailContent('assortment');
}

function renderDecisionTree() {
    renderKpiCards();
    if (activeKpi === 'compliance') renderKpiDetailContent('compliance');
}
