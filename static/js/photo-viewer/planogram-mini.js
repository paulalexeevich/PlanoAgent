/* Photo Viewer — Recognition-based mini planogram rendering. */

function fetchAndRenderPlanograms() {
    fetch('/api/build-from-recognition', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
        .then(r => r.json())
        .then(data => {
            if (data.status !== 'success' || !data.planogram) {
                console.warn('[plano-mini] Build failed:', data.error);
                return;
            }
            PV.recog.planogramData = data.planogram;
            PV.recog.productsMap = {};
            (PV.recog.planogramData.products || []).forEach(p => { PV.recog.productsMap[p.id] = p; });

            const bays = PV.recog.planogramData.equipment.bays || [];
            const sortedPhotos = [...PV.photos].sort();
            PV.recog.bayMap = {};
            bays.forEach((bay, idx) => {
                const photoName = sortedPhotos[idx];
                if (photoName) PV.recog.bayMap[photoName] = bay;
            });

            zoomFitAll();
            renderAllMiniPlanograms();
        })
        .catch(err => console.error('[plano-mini] Fetch error:', err));
}

function renderAllMiniPlanograms() {
    if (!PV.recog.planogramData || !PV.recog.planogramData.equipment) return;

    Object.keys(PV.recog.bayMap).forEach(photoName => {
        const container = document.getElementById(`plano-${photoName}`);
        if (!container) return;
        renderMiniBay(container, PV.recog.bayMap[photoName], photoName);
    });
}

function getPlanoScaleForPhoto(photoName, bayWidthIn) {
    const img = document.getElementById(`img-${photoName}`);
    if (!img) return 3;
    const photoDisplayW = img.offsetWidth || img.clientWidth;
    if (photoDisplayW < 20) return 3;
    return photoDisplayW / bayWidthIn;
}

function renderMiniBay(container, bay, photoName) {
    container.innerHTML = '';
    const bayWidthIn = bay.width_in || 49.21;
    const sc = getPlanoScaleForPhoto(photoName, bayWidthIn);

    const bays = BayRenderer.normalizeDashboard({ bays: [bay] });
    const layout = BayRenderer.render({
        container,
        scale: sc,
        bayGap: 0,
        gluedGap: 0,
        bays,
        onShelf(shelfEl, shelf, si, bayObj, bayIdx) {
            const hasProducts = shelf.positions && shelf.positions.length > 0;
            if (!hasProducts) {
                shelfEl.classList.add('empty-shelf');
                const lbl = document.createElement('span');
                lbl.className = 'empty-shelf-label';
                lbl.textContent = 'Empty';
                shelfEl.appendChild(lbl);
            }
        },
    });

    if (!layout || !layout.length) return;

    const productLayer = document.createElement('div');
    productLayer.className = 'product-layer';
    container.appendChild(productLayer);

    requestAnimationFrame(() => {
        const containerRect = container.getBoundingClientRect();
        const meta = layout[0];
        if (!meta || !meta.bodyEl) return;

        bays[0].shelves.forEach(shelf => {
            const sMeta = meta.shelves.find(s => s.shelf_number === shelf.shelf_number);
            if (!sMeta || !sMeta.el) return;
            const positions = shelf.positions || [];
            if (!positions.length) return;

            const shelfRect = sMeta.el.getBoundingClientRect();
            const shelfTopPx = shelfRect.top - containerRect.top;
            const shelfHeight = shelfRect.height;
            const bodyRect = meta.bodyEl.getBoundingClientRect();
            const bodyLeftPx = bodyRect.left - containerRect.left;

            positions.forEach(pos => {
                if (pos._phantom) return;
                const product = PV.recog.productsMap[pos.product_id];
                if (!product) return;

                const singleWidth = product.width_in * sc;
                const blockHeight = Math.min(product.height_in * sc, shelfHeight - 2);
                const baseLeft = pos.x_position * sc;

                for (let f = 0; f < (pos.facings_wide || 1); f++) {
                    const block = document.createElement('div');
                    block.className = 'product-block';
                    if (f > 0) block.classList.add('facing-repeat');

                    block.dataset.art = product.name || '';
                    block.dataset.productId = pos.product_id || '';

                    const leftPx = bodyLeftPx + baseLeft + f * singleWidth;
                    block.style.width = singleWidth + 'px';
                    block.style.height = blockHeight + 'px';
                    block.style.left = leftPx + 'px';
                    block.style.top = (shelfTopPx + shelfHeight - blockHeight) + 'px';

                    const hasNoBg = !!product.image_no_bg_url;
                    const imgSrc = product.image_no_bg_url || product.image_url;

                    if (imgSrc && blockHeight > 14 && singleWidth > 10) {
                        block.classList.add('product-block-image');
                        if (hasNoBg) {
                            block.classList.add('product-no-bg');
                        }
                        const imgEl = document.createElement('img');
                        imgEl.src = imgSrc;
                        imgEl.className = 'product-image';
                        imgEl.draggable = false;
                        block.appendChild(imgEl);
                    } else {
                        block.style.backgroundColor = product.color_hex || '#666';
                    }

                    block.style.cursor = 'pointer';
                    block.addEventListener('click', (e) => {
                        e.stopPropagation();
                        selectRealogramProduct(product.name || '', pos.product_id || '');
                    });

                    productLayer.appendChild(block);
                }
            });
        });

        applyRealogramColorMode();
        if (PV.selection.art) highlightSelected();
    });
}
