/* EQUIPMENT EDITOR — Direct manipulation editor overlay */

let EDITOR_SCALE = 3;
let editorState = null;
let _edDrag = null;

function editorZoom(dir) {
    EDITOR_SCALE = Math.max(1, Math.min(8, EDITOR_SCALE + dir * 0.5));
    syncEditorScaleUI();
    renderEditorBays();
}

function syncEditorScaleUI() {
    const slider = document.getElementById('edScaleSlider');
    const label = document.getElementById('edScaleValue');
    if (slider) slider.value = EDITOR_SCALE;
    if (label) label.textContent = EDITOR_SCALE + 'px/' + dUnit();
}

function initEditorScaleSlider() {
    const slider = document.getElementById('edScaleSlider');
    if (!slider) return;
    slider.addEventListener('input', (e) => {
        EDITOR_SCALE = parseFloat(e.target.value);
        syncEditorScaleUI();
        renderEditorBays();
    });
}

function _defaultEditorState() {
    return {
        equipment_type: 'gondola',
        height_in: 72,
        depth_in: 24,
        bays: [
            { width_in: 48, num_shelves: 5, shelf_clearances: null },
            { width_in: 48, num_shelves: 5, shelf_clearances: null },
            { width_in: 48, num_shelves: 5, shelf_clearances: null }
        ]
    };
}

function initEditorState() {
    if (planogramData && planogramData.equipment && planogramData.equipment.bays && planogramData.equipment.bays.length > 0) {
        const eq = planogramData.equipment;
        const firstBay = eq.bays[0];
        editorState = {
            equipment_type: eq.equipment_type || 'gondola',
            height_in: firstBay.height_in || 72,
            depth_in: firstBay.depth_in || 24,
            bays: eq.bays.map(bay => {
                const sorted = bay.shelves ? [...bay.shelves].sort((a, b) => a.y_position - b.y_position) : [];
                const clearances = sorted.length > 0 ? sorted.map(s => s.height_in) : null;
                return { width_in: bay.width_in || 48, num_shelves: sorted.length || 5, shelf_clearances: clearances, glued_right: !!bay.glued_right };
            })
        };
    } else {
        editorState = _defaultEditorState();
    }
}

function initEditorDragHandlers() {
    document.addEventListener('mousemove', _edOnMove);
    document.addEventListener('mouseup', _edOnUp);
}

function _edOnMove(e) {
    if (!_edDrag) return;
    const tooltip = document.getElementById('edDimTooltip');
    const MIN_SHELF = 2, MIN_BAY = 12;

    if (_edDrag.type === 'width') {
        const rawDelta = Math.round((e.clientX - _edDrag.startX) / EDITOR_SCALE);
        const deltaIn  = _edDrag.side === 'left' ? -rawDelta : rawDelta;
        const bay = editorState.bays[_edDrag.bayIdx];
        bay.width_in = Math.max(MIN_BAY, _edDrag.startValue + deltaIn);
        _edLiveWidth(_edDrag.bayIdx);
        tooltip.textContent = dFmt(bay.width_in);
    } else {
        const deltaIn = Math.round((_edDrag.startY - e.clientY) / EDITOR_SCALE);
        const bay = editorState.bays[_edDrag.bayIdx];
        const si = _edDrag.shelfIdx;
        const siBelow = si - 1;

        const maxUp   = _edDrag.startValue - MIN_SHELF;
        const maxDown = _edDrag.startValueBelow - MIN_SHELF;
        const clamped = Math.max(-maxDown, Math.min(maxUp, deltaIn));

        bay.shelf_clearances[si]      = _edDrag.startValue      - clamped;
        bay.shelf_clearances[siBelow] = _edDrag.startValueBelow + clamped;

        _edLiveShelfH(_edDrag.bayIdx);
        const hBelow = bay.shelf_clearances[siBelow];
        const hAbove = bay.shelf_clearances[si];
        tooltip.textContent = dFmt(hBelow) + ' | ' + dFmt(hAbove);
    }

    tooltip.style.display = 'block';
    tooltip.style.left = (e.clientX + 14) + 'px';
    tooltip.style.top  = (e.clientY - 26) + 'px';
}

function _edOnUp() {
    if (!_edDrag) return;
    if (_edDrag.handle) _edDrag.handle.classList.remove('dragging');
    
    _edDrag = null;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    document.getElementById('edDimTooltip').style.display = 'none';
    renderEditorBays();
}

function _edStartWidth(e, bayIdx, side) {
    e.preventDefault();
    const handle = e.currentTarget;
    handle.classList.add('dragging');

    _edDrag = {
        type: 'width', side: side || 'right',
        bayIdx,
        startX:     e.clientX,
        startValue: editorState.bays[bayIdx].width_in,
        handle
    };
    document.body.style.cursor = 'ew-resize';
    document.body.style.userSelect = 'none';
}

function _edStartHeight(e, bayIdx, shelfIdx) {
    e.preventDefault();
    const bay = editorState.bays[bayIdx];
    if (!bay.shelf_clearances) {
        const h = _edHeightIn();
        const even = Math.round(h / bay.num_shelves);
        bay.shelf_clearances = Array(bay.num_shelves).fill(even);
    }
    const handle = e.currentTarget;
    handle.classList.add('dragging');
    _edDrag = {
        type: 'height',
        bayIdx, shelfIdx,
        startY:          e.clientY,
        startValue:      bay.shelf_clearances[shelfIdx],
        startValueBelow: bay.shelf_clearances[shelfIdx - 1],
        handle
    };
    document.body.style.cursor = 'ns-resize';
    document.body.style.userSelect = 'none';
}

function _edLiveWidth(bayIdx) {
    const bay = editorState.bays[bayIdx];
    const w   = bay.width_in;
    const wpx = w * EDITOR_SCALE;
    const heightIn = _edHeightIn();
    const wrapper = document.querySelector(`.eq-bay-wrapper[data-idx="${bayIdx}"]`);
    if (!wrapper) return;

    wrapper.style.width = wpx + 'px';

    if (_edDrag && _edDrag.side === 'left' && _edDrag.bayIdx === bayIdx) {
        const offsetPx = _edDrag.startValue * EDITOR_SCALE - wpx;
        wrapper.style.marginLeft = offsetPx + 'px';
    } else {
        wrapper.style.marginLeft = '';
    }

    const bayEl = wrapper.querySelector('.eq-editor-bay');
    if (bayEl) {
        bayEl.style.width = wpx + 'px';
        const title = bayEl.querySelector('.bay-hdr-title');
        if (title) title.textContent = `Bay ${bayIdx + 1}`;
        const footerEl = bayEl.querySelector('.bay-footer');
        if (footerEl) footerEl.textContent = dFmt(w);
        const body = bayEl.querySelector('.eq-editor-bay-body');
        if (body) body.style.width = wpx + 'px';
    }
}

function _edLiveShelfH(bayIdx) {
    const bay = editorState.bays[bayIdx];
    if (!bay.shelf_clearances) return;
    const wrapper = document.querySelector(`.eq-bay-wrapper[data-idx="${bayIdx}"]`);
    if (!wrapper) return;
    const shelfEls = wrapper.querySelectorAll('.eq-editor-shelf');
    let yPos = 0;
    bay.shelf_clearances.forEach((h, si) => {
        if (shelfEls[si]) {
            shelfEls[si].style.bottom = (yPos * EDITOR_SCALE) + 'px';
            shelfEls[si].style.height = (h * EDITOR_SCALE) + 'px';
            const dl = shelfEls[si].querySelector('.shelf-drag-line');
            if (dl) dl.dataset.dim = Math.round(h) + '"';
            const lbl = shelfEls[si].querySelector('.eq-editor-shelf-label');
            if (lbl) lbl.textContent = `S${si + 1} — ${dFmt(h)}`;
        }
        yPos += h;
    });
}

function openEquipmentEditor() {
    initEditorState();
    document.getElementById('edEqType').value = editorState.equipment_type;
    document.getElementById('edEqHeight').value = useMetric ? d(editorState.height_in) : editorState.height_in;
    document.getElementById('edEqDepth').value = useMetric ? d(editorState.depth_in) : editorState.depth_in;
    document.getElementById('edBayCount').textContent = editorState.bays.length;
    document.getElementById('edRemoveBayBtn').disabled = editorState.bays.length <= 1;
    toggleAllBaysPopover(false);
    syncEditorUnitToggle();
    syncEditorScaleUI();
    syncEditorUnitLabels();
    renderEditorBays();
    document.getElementById('eqEditorOverlay').classList.add('open');
}

function syncEditorUnitToggle() {
    document.getElementById('edUnitIn').classList.toggle('active', !useMetric);
    document.getElementById('edUnitCm').classList.toggle('active', useMetric);
}

function syncEditorUnitLabels() {
    const u = dUnit();
    document.querySelectorAll('.ed-unit-label').forEach(el => { el.textContent = u; });
    const abpLabel = document.getElementById('abpWidthLabel');
    if (abpLabel) abpLabel.textContent = `Width (${u})`;
}

function _edHeightIn() {
    const raw = parseFloat(document.getElementById('edEqHeight').value) || 72;
    return useMetric ? raw / IN_TO_CM : raw;
}

function closeEquipmentEditor() {
    document.getElementById('eqEditorOverlay').classList.remove('open');
    toggleAllBaysPopover(false);
}

function renderEditorBays() {
    const container = document.getElementById('editorBaysContainer');
    container.innerHTML = '';
    const heightIn = _edHeightIn();

    editorState.bays.forEach((bay, idx) => {
        const numShelves = bay.num_shelves || 5;

        const wrapper = document.createElement('div');
        wrapper.className = 'eq-bay-wrapper';
        wrapper.dataset.idx = idx;
        wrapper.style.width = (bay.width_in * EDITOR_SCALE) + 'px';
        wrapper.style.marginLeft = '';

        const bayEl = document.createElement('div');
        bayEl.className = 'eq-editor-bay';
        bayEl.style.width = (bay.width_in * EDITOR_SCALE) + 'px';
        bayEl.style.position = 'relative';

        const hdr = document.createElement('div');
        hdr.className = 'eq-editor-bay-hdr';
        hdr.innerHTML = `
            <span class="bay-hdr-title">Bay ${idx + 1}</span>
            <div class="bay-shelf-ctrl">
                <button class="bsc-btn" title="Remove shelf">−</button>
                <span class="bsc-val">${numShelves}S</span>
                <button class="bsc-btn" title="Add shelf">+</button>
            </div>`;
        hdr.querySelectorAll('.bsc-btn')[0].addEventListener('click', e => { e.stopPropagation(); editorRemoveShelf(idx); });
        hdr.querySelectorAll('.bsc-btn')[1].addEventListener('click', e => { e.stopPropagation(); editorAddShelf(idx); });
        bayEl.appendChild(hdr);

        const body = document.createElement('div');
        body.className = 'eq-editor-bay-body';
        body.style.height = (heightIn * EDITOR_SCALE) + 'px';
        body.style.width = (bay.width_in * EDITOR_SCALE) + 'px';
        body.style.position = 'relative';
        body.style.overflow = 'hidden';

        const clearances = bay.shelf_clearances;
        const _buildShelf = (si, bottomPx, heightPx, shelfH) => {
            const shelfEl = document.createElement('div');
            shelfEl.className = 'eq-editor-shelf';
            shelfEl.style.bottom = bottomPx + 'px';
            shelfEl.style.height = heightPx + 'px';
            shelfEl.style.position = 'absolute';
            shelfEl.style.width = '100%';

            const lbl = document.createElement('span');
            lbl.className = 'eq-editor-shelf-label';
            lbl.textContent = `S${si + 1} — ${dFmt(shelfH)}`;
            shelfEl.appendChild(lbl);

            if (si > 0) {
                const dragLine = document.createElement('div');
                dragLine.className = 'shelf-drag-line';
                dragLine.dataset.dim = Math.round(shelfH) + '"';
                dragLine.addEventListener('mousedown', e => _edStartHeight(e, idx, si));
                shelfEl.appendChild(dragLine);
            }

            body.appendChild(shelfEl);
        };

        if (clearances && clearances.length > 0) {
            let yPos = 0;
            clearances.forEach((h, si) => {
                _buildShelf(si, yPos * EDITOR_SCALE, h * EDITOR_SCALE, h);
                yPos += h;
            });
        } else {
            const shelfH = heightIn / numShelves;
            for (let si = 0; si < numShelves; si++) {
                _buildShelf(si, si * shelfH * EDITOR_SCALE, shelfH * EDITOR_SCALE, shelfH);
            }
        }

        bayEl.appendChild(body);

        const footer = document.createElement('div');
        footer.className = 'bay-footer';
        footer.textContent = dFmt(bay.width_in);
        bayEl.appendChild(footer);

        const edgeHandleLeft = document.createElement('div');
        edgeHandleLeft.className = 'bay-edge-handle-left';
        edgeHandleLeft.addEventListener('mousedown', e => _edStartWidth(e, idx, 'left'));
        bayEl.appendChild(edgeHandleLeft);

        const edgeHandle = document.createElement('div');
        edgeHandle.className = 'bay-edge-handle';
        edgeHandle.addEventListener('mousedown', e => _edStartWidth(e, idx, 'right'));
        bayEl.appendChild(edgeHandle);

        wrapper.appendChild(bayEl);

        if (idx > 0) {
            const gluedToPrev = editorState.bays[idx - 1].glued_right;
            wrapper.style.marginLeft = gluedToPrev ? '0' : '12px';
        }

        container.appendChild(wrapper);

        if (idx < editorState.bays.length - 1) {
            const toggle = document.createElement('div');
            toggle.className = 'bay-glue-toggle' + (bay.glued_right ? ' glued' : '');
            toggle.title = bay.glued_right ? 'Unglue bays' : 'Glue bays together';
            toggle.innerHTML = `<span class="glue-icon">${bay.glued_right ? '🔗' : '⋯'}</span>`;
            toggle.addEventListener('click', () => toggleBayGlue(idx));
            container.appendChild(toggle);
        }
    });
}

function toggleBayGlue(bayIdx) {
    const bay = editorState.bays[bayIdx];
    bay.glued_right = !bay.glued_right;
    renderEditorBays();
}

function _redistributeClearances(bay, newCount, heightIn) {
    const base = 6, thickness = 1;
    const totalAvailable = heightIn - base - (newCount * thickness);
    if (totalAvailable <= 0) {
        bay.shelf_clearances = Array(newCount).fill(Math.max(2, Math.round(heightIn / newCount)));
    } else {
        const even = parseFloat((totalAvailable / newCount).toFixed(1));
        bay.shelf_clearances = Array(newCount).fill(even);
    }
    bay.num_shelves = newCount;
}

function editorAddShelf(bayIdx) {
    const bay = editorState.bays[bayIdx];
    const newCount = Math.min(12, (bay.num_shelves || 5) + 1);
    if (newCount === bay.num_shelves) return;
    _redistributeClearances(bay, newCount, _edHeightIn());
    renderEditorBays();
}

function editorRemoveShelf(bayIdx) {
    const bay = editorState.bays[bayIdx];
    const newCount = Math.max(1, (bay.num_shelves || 5) - 1);
    if (newCount === bay.num_shelves) return;
    const heightIn = _edHeightIn();
    _redistributeClearances(bay, newCount, heightIn);
    renderEditorBays();
}

function editorAddBay() {
    const last = editorState.bays[editorState.bays.length - 1] || { width_in: 48, num_shelves: 5, shelf_clearances: null };
    editorState.bays.push({ ...last, shelf_clearances: last.shelf_clearances ? [...last.shelf_clearances] : null });
    document.getElementById('edBayCount').textContent = editorState.bays.length;
    document.getElementById('edRemoveBayBtn').disabled = editorState.bays.length <= 1;
    renderEditorBays();
}

function editorRemoveBay() {
    if (editorState.bays.length <= 1) return;
    editorState.bays.pop();
    document.getElementById('edBayCount').textContent = editorState.bays.length;
    document.getElementById('edRemoveBayBtn').disabled = editorState.bays.length <= 1;
    renderEditorBays();
}

function toggleAllBaysPopover(forceState) {
    const popover = document.getElementById('allBaysPopover');
    const btn = document.getElementById('edAllBaysBtn');
    const show = forceState !== undefined ? !!forceState : !popover.classList.contains('open');
    popover.classList.toggle('open', show);
    btn.classList.toggle('active', show);
    if (show) {
        const first = editorState.bays[0] || { width_in: 48, num_shelves: 5, shelf_clearances: null };
        document.getElementById('abpWidth').value = first.width_in;
        document.getElementById('abpShelves').value = first.num_shelves;
        document.getElementById('abpHeights').value = first.shelf_clearances ? first.shelf_clearances.join(', ') : '';
    }
}

function applyAllBaysConfig() {
    const width = parseFloat(document.getElementById('abpWidth').value);
    const shelves = parseInt(document.getElementById('abpShelves').value);
    const heightsStr = document.getElementById('abpHeights').value.trim();
    const clearances = heightsStr
        ? heightsStr.split(',').map(h => { const n = parseFloat(h.trim()); return isNaN(n) ? null : n; }).filter(h => h !== null)
        : null;
    const patch = {
        width_in: isNaN(width) ? 48 : Math.max(12, width),
        num_shelves: isNaN(shelves) ? 5 : Math.max(1, shelves),
        shelf_clearances: (clearances && clearances.length > 0) ? clearances : null
    };
    editorState.bays = editorState.bays.map(() => ({ ...patch }));
    toggleAllBaysPopover(false);
    renderEditorBays();
}

async function applyEquipmentEditor() {
    editorState.equipment_type = document.getElementById('edEqType').value;
    editorState.height_in = toInches(document.getElementById('edEqHeight').value) || 72;
    editorState.depth_in = toInches(document.getElementById('edEqDepth').value) || 24;

    const config = {
        equipment_type: editorState.equipment_type,
        num_bays: editorState.bays.length,
        num_shelves: editorState.bays[0] ? editorState.bays[0].num_shelves : 5,
        bay_width: editorState.bays[0] ? editorState.bays[0].width_in : 48,
        bay_height: editorState.height_in,
        bay_depth: editorState.depth_in,
        bays_config: editorState.bays.map(bay => ({
            width_in: bay.width_in,
            num_shelves: bay.num_shelves,
            shelf_clearances: bay.shelf_clearances,
            glued_right: !!bay.glued_right
        }))
    };

    const applyBtn = document.getElementById('eqEditorApplyBtn');
    const applyLabel = document.getElementById('eqEditorApplyLabel');
    const applySpinner = document.getElementById('eqEditorApplySpinner');
    applyBtn.disabled = true;
    applyLabel.textContent = 'Generating...';
    applySpinner.style.display = 'inline-block';
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
        closeEquipmentEditor();
    } catch (err) {
        console.error('Equipment editor apply failed:', err);
        showError('Equipment generation failed: ' + err.message);
    }

    applyBtn.disabled = false;
    applyLabel.textContent = 'Generate Equipment';
    applySpinner.style.display = 'none';
}
