/* Photo Viewer — Detail panel builders and selection handlers. */

function countFacingsForArt(art) {
    let total = 0;
    const breakdown = [];
    PV.photos.forEach(name => {
        const d = PV.photoData[name];
        if (!d) return;
        const cnt = d.products.filter(pp => pp.art === art).length;
        if (cnt > 0) {
            total += cnt;
            breakdown.push({ name, count: cnt });
        }
    });
    return { total, breakdown };
}

function buildDetailHeader(fullName, thumbUrl, options) {
    const { brand, category, price } = options || {};
    let html = `<div class="detail-header">`;
    if (thumbUrl) {
        html += `<img class="detail-thumb" src="${thumbUrl}" alt="${fullName}" onerror="this.style.display='none'">`;
    }
    html += `<div class="detail-header-info">`;
    html += `<div class="field-value" style="font-weight:600;font-size:12px;margin-bottom:4px;line-height:1.3">${fullName}</div>`;
    html += `<div style="margin-bottom:4px">`;
    if (brand) html += `<span class="tag tag-brand">${brand}</span>`;
    if (category) html += `<span class="tag tag-category">${category}</span>`;
    html += `</div>`;
    if (price) html += `<span class="tag tag-price">${price} ₽</span>`;
    html += `</div></div>`;
    return html;
}

function buildStatusBadge(type) {
    const badges = {
        'in-plano':     '<span class="tag-plano" style="font-size:11px;padding:3px 8px">In Planogram</span>',
        'not-in-plano': '<span class="tag-alert" style="font-size:11px;padding:3px 8px">Not in Planogram</span>',
        'out-of-shelf': '<span class="tag-oos" style="font-size:11px;padding:3px 8px">Out of Shelf</span>',
    };
    return `<div class="field" style="margin-bottom:12px">${badges[type] || ''}</div>`;
}

function buildFacingsGrid(planoFacings, photoFacings, inPlano) {
    const planoDisplay = inPlano ? planoFacings : '—';
    const photoStyle = photoFacings === 0 ? ' style="color:#ef4444"' : '';
    return `
        <div class="field">
            <div class="field-label">Facings Comparison</div>
            <div class="dims-grid" style="margin-top:4px">
                <span class="dim-label">Planogram</span><span class="dim-value">${planoDisplay}</span>
                <span class="dim-label">On Shelf (photos)</span><span class="dim-value"${photoStyle}>${photoFacings}</span>
            </div>
        </div>
    `;
}

function buildSalesSection(sd) {
    if (!sd) return '';
    return `
        <div class="field">
            <div class="field-label">Sales Data (weekly avg)</div>
            <div class="dims-grid" style="margin-top:4px">
                <span class="dim-label">Avg Sale ₽</span><span class="dim-value" style="color:#4ecdc4;font-weight:600">${sd.avg_sale_amount.toLocaleString('ru-RU', {minimumFractionDigits: 0, maximumFractionDigits: 0})} ₽</span>
                <span class="dim-label">Avg Qty</span><span class="dim-value">${sd.avg_sale_qty.toFixed(1)}</span>
                <span class="dim-label">Avg Stock</span><span class="dim-value">${sd.avg_stock_qty.toFixed(1)}</span>
                <span class="dim-label">Weeks</span><span class="dim-value">${sd.weeks}</span>
            </div>
        </div>
    `;
}

function buildSpmSection(art, productId) {
    const spmData = PV.salesPerMeter.map[art] || (productId && PV.salesPerMeter.map[productId]);
    if (!spmData || PV.salesPerMeter.avg <= 0) return '';
    const spm = spmData.salesPerMeter;
    const pctDiff = ((spm - PV.salesPerMeter.avg) / PV.salesPerMeter.avg) * 100;
    const pctSign = pctDiff >= 0 ? '+' : '';
    const pctColor = pctDiff >= 50 ? '#ef4444' : pctDiff <= -50 ? '#f59e0b' : '#22c55e';
    return `
        <div class="field">
            <div class="field-label">₽ / Meter (shelf efficiency)</div>
            <div class="dims-grid" style="margin-top:4px">
                <span class="dim-label">₽/meter</span><span class="dim-value" style="color:${spmData.color};font-weight:600">${spm.toLocaleString('ru-RU', {maximumFractionDigits: 0})} ₽</span>
                <span class="dim-label">Avg (all SKUs)</span><span class="dim-value">${PV.salesPerMeter.avg.toLocaleString('ru-RU', {maximumFractionDigits: 0})} ₽</span>
                <span class="dim-label">vs Average</span><span class="dim-value" style="color:${pctColor};font-weight:600">${pctSign}${pctDiff.toFixed(0)}%</span>
            </div>
        </div>
    `;
}

function selectProduct(photoName, idx) {
    const data = PV.photoData[photoName];
    const p = data.products[idx];
    PV.selection.id = p._id;
    PV.selection.photoName = photoName;
    PV.selection.art = p.art;

    const { total: totalPhotoFacings, breakdown: photoBreakdown } = countFacingsForArt(p.art);
    const pf = PV.planogramFacings[p.art];
    const inPlano = !!pf;
    const fullName = p.full_name || p.display_name || p.art;

    let html = buildDetailHeader(fullName, p.miniature_url || '', {
        brand: p.brand_name, category: p.category_name, price: p.price,
    });
    html += buildStatusBadge(inPlano ? 'in-plano' : 'not-in-plano');
    html += buildFacingsGrid(pf ? pf.facings_wide : 0, totalPhotoFacings, inPlano);

    if (photoBreakdown.length > 0) {
        html += `<div class="field"><div class="field-label">Per Photo</div>`;
        photoBreakdown.forEach(pb => {
            html += `<div style="font-size:11px;color:#ccc;margin-top:2px">${pb.name}: <strong>${pb.count}</strong> facing${pb.count > 1 ? 's' : ''}</div>`;
        });
        html += `</div>`;
    }
    if (p.barcode) {
        html += `<div class="field"><div class="field-label">Barcode</div><div class="field-value" style="font-family:monospace;font-size:11px">${p.barcode}</div></div>`;
    }
    if (p.facing_width_cm) {
        html += `<div class="field"><div class="field-label">Size (cm)</div><div class="field-value" style="font-size:11px">${p.facing_width_cm.toFixed(1)} × ${p.facing_height_cm.toFixed(1)}</div></div>`;
    }

    html += buildSalesSection(PV.salesData[p.art] || PV.salesData[p.product_id]);
    html += buildSpmSection(p.art, p.product_id);

    document.getElementById('detailContent').innerHTML = html;
    openPanelTab('analytics');
    highlightSelected();
    highlightListItem();
}

function selectOutOfShelfProduct(art) {
    PV.selection.id = null;
    PV.selection.photoName = null;
    PV.selection.art = art;

    const pf = PV.planogramFacings[art];
    if (!pf) return;

    let html = buildDetailHeader(pf.name || art, pf.image_url || '', { brand: pf.brand });
    html += buildStatusBadge('out-of-shelf');
    html += buildFacingsGrid(pf.facings_wide, 0, true);

    if (pf.width_cm) {
        html += `<div class="field"><div class="field-label">Size (cm)</div><div class="field-value" style="font-size:11px">${pf.width_cm.toFixed(1)} × ${pf.height_cm.toFixed(1)}</div></div>`;
    }

    html += buildSalesSection(PV.salesData[art]);
    html += buildSpmSection(art);

    document.getElementById('detailContent').innerHTML = html;
    openPanelTab('analytics');
    highlightListItem();
}

function selectRealogramProduct(art, productId) {
    PV.selection.id = null;
    PV.selection.photoName = null;
    PV.selection.art = art;

    const pf = PV.planogramFacings[art];
    const { total: totalPhotoFacings } = countFacingsForArt(art);
    const product = PV.recog.productsMap[productId];
    const fullName = (product && (product.full_name || product.name)) || art;
    const thumbUrl = (product && (product.image_no_bg_url || product.image_url)) || '';

    let html = buildDetailHeader(fullName, thumbUrl);
    html += buildStatusBadge(pf ? 'in-plano' : 'not-in-plano');
    html += buildFacingsGrid(pf ? pf.facings_wide : 0, totalPhotoFacings, !!pf);
    html += buildSalesSection(PV.salesData[art]);
    html += buildSpmSection(art);

    document.getElementById('detailContent').innerHTML = html;
    openPanelTab('analytics');
    highlightSelected();
    highlightListItem();
}

function selectShelf(photoName, idx) {
    const data = PV.photoData[photoName];
    const s = data.shelves[idx];
    PV.selection.id = s._id;
    PV.selection.photoName = photoName;

    const html = `
        <span class="tag tag-photo">${photoName}</span><br><br>
        <div class="field">
            <div class="field-label">Type</div>
            <div class="field-value">Shelf Line ${idx + 1}</div>
        </div>
        <div class="field">
            <div class="field-label">Line Coordinates</div>
            <div class="field-value" style="font-family:monospace">
                (${s.x1}, ${s.y1}) &rarr; (${s.x2}, ${s.y2})
                <br>Width: ${s.x2 - s.x1} px
            </div>
        </div>
        <div class="field">
            <div class="field-label">Line Type</div>
            <div class="field-value">${s.line_type || 'raw'}</div>
        </div>
        <div class="field">
            <div class="field-label">Approved</div>
            <div class="field-value">${s.approved ? 'Yes' : 'No'}</div>
        </div>
        <div class="field">
            <div class="field-label">ID</div>
            <div class="field-value" style="font-family:monospace;font-size:10px">${s._id}</div>
        </div>
    `;
    document.getElementById('detailContent').innerHTML = html;
    openPanelTab('analytics');
    highlightSelected();
}

function clearSelection() {
    PV.selection.id = null;
    PV.selection.photoName = null;
    PV.selection.art = null;
    document.getElementById('detailContent').innerHTML =
        '<div class="empty-state">Click a bounding box to see details</div>';
    highlightSelected();
    highlightListItem();
}

function highlightListItem() {
    document.querySelectorAll('.product-list-item').forEach(el => {
        el.classList.remove('selected');
    });
    if (PV.selection.art && !PV.selection.id) {
        const el = document.querySelector(`.product-list-item[data-art="${PV.selection.art}"]`);
        if (el) el.classList.add('selected');
    } else if (PV.selection.id && PV.selection.photoName) {
        const data = PV.photoData[PV.selection.photoName];
        if (data) {
            const p = data.products.find(pp => pp._id === PV.selection.id);
            if (p) {
                const el = document.querySelector(`.product-list-item[data-art="${p.art}"]`);
                if (el) el.classList.add('selected');
            }
        }
    }
}
