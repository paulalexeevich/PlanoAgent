/* PLANOGRAM RENDERER — Dashboard visualization (uses shared BayRenderer)
 *
 * Three-layer architecture:
 *   1. Equipment layer — bay borders, shelves, labels (BayRenderer)
 *   2. Product layer   — per-bay clip containers with overflow:hidden.
 *      Each product (including phantom cross-bay duplicates) renders at
 *      its own shelf's actual height.  Overflow is clipped at bay edges
 *      so misaligned shelves display correctly.
 *   3. Bay border overlay — thin lines on top of products.
 *
 * Product positioning deferred to requestAnimationFrame so the browser
 * has completed layout of the equipment layer first, making
 * getBoundingClientRect reliable.
 */

function renderPlanogram() {
    const container = document.getElementById('planogramContainer');
    if (!planogramData || !planogramData.equipment) {
        container.innerHTML = '';
        return;
    }

    const isDtLayer    = currentLayer.startsWith('dt-');
    const dtLevelIdx   = isDtLayer ? parseInt(currentLayer.split('-')[1]) : -1;
    const dtLevel      = isDtLayer && decisionTreeData && decisionTreeData.levels
        ? decisionTreeData.levels[dtLevelIdx] : null;
    const dtLevelName  = dtLevel ? dtLevel.name : null;
    const dtPalette    = dtLevelName ? buildDtPaletteForLevel(dtLevelName) : {};

    renderLayerLegend(dtLevelName, dtPalette);

    const bays = BayRenderer.normalizeDashboard(planogramData.equipment);

    container.classList.toggle('show-dimensions', showDimensions);

    // ── LAYER 1: Equipment (bays, shelves, borders — no products) ──
    const layout = BayRenderer.render({
        container,
        scale,
        bayGap:   4,
        gluedGap: -2,
        bays,

        onShelf(shelfEl, shelf, si, bay, bayIdx) {
            const hasProducts = shelf.positions && shelf.positions.length > 0;
            const hasReal = hasProducts && shelf.positions.some(p => !p._phantom);
            if (!hasReal) {
                shelfEl.classList.add('empty-shelf');
                const emptyLabel = document.createElement('span');
                emptyLabel.className = 'empty-shelf-label';
                emptyLabel.textContent = 'Empty';
                shelfEl.appendChild(emptyLabel);
            }
        },
    });

    if (!layout || !layout.length) return;

    const borderOverlay = document.createElement('div');
    borderOverlay.className = 'bay-border-overlay';
    container.appendChild(borderOverlay);

    // Defer product + border-overlay rendering until browser has completed layout
    requestAnimationFrame(() => {
        const containerRect = container.getBoundingClientRect();

        bays.forEach((bay, bayIdx) => {
            const meta = layout[bayIdx];
            if (!meta || !meta.bodyEl) return;

            const bodyRect   = meta.bodyEl.getBoundingClientRect();
            const bodyLeftPx = bodyRect.left - containerRect.left;
            const bodyTopPx  = bodyRect.top  - containerRect.top;
            const bodyWPx    = bodyRect.width;
            const bodyHPx    = bodyRect.height;

            // Per-bay product clip container
            const bayProductClip = document.createElement('div');
            bayProductClip.className = 'bay-product-clip';
            bayProductClip.style.position = 'absolute';
            bayProductClip.style.left     = bodyLeftPx + 'px';
            bayProductClip.style.top      = bodyTopPx + 'px';
            bayProductClip.style.width    = bodyWPx + 'px';
            bayProductClip.style.height   = bodyHPx + 'px';
            bayProductClip.style.overflow = 'hidden';
            bayProductClip.style.pointerEvents = 'none';
            bayProductClip.style.zIndex   = '3';
            container.appendChild(bayProductClip);

            bay.shelves.forEach((shelf) => {
                const sMeta = meta.shelves.find(s => s.shelf_number === shelf.shelf_number);
                if (!sMeta || !sMeta.el) return;

                const positions = shelf.positions || [];
                if (!positions.length) return;

                const shelfRect   = sMeta.el.getBoundingClientRect();
                const shelfTopPx  = shelfRect.top  - bodyRect.top;
                const shelfHeight = shelfRect.height;

                positions.forEach((pos) => {
                    const product = productsMap[pos.product_id];
                    if (!product) return;

                    const singleWidth = product.width_in * scale;
                    const blockHeight = Math.min(product.height_in * scale, shelfHeight - 4);
                    const baseLeft    = pos.x_position * scale;

                    for (let f = 0; f < pos.facings_wide; f++) {
                        const block = document.createElement('div');
                        block.className = 'product-block';
                        if (f > 0) block.classList.add('facing-repeat');

                        const leftPx  = baseLeft + f * singleWidth;
                        const widthPx = singleWidth;

                        block.style.width  = widthPx + 'px';
                        block.style.height = blockHeight + 'px';
                        block.style.left   = leftPx + 'px';
                        block.style.top    = (shelfTopPx + shelfHeight - blockHeight) + 'px';

                        const labelEl = document.createElement('div');
                        labelEl.className = 'product-label';

                        if (isDtLayer && dtLevelName) {
                            const groups   = dtPositionMap[pos.product_id];
                            const groupVal = groups ? (groups[dtLevelName] || '?') : '?';
                            const color    = dtPalette[groupVal] || '#666';
                            block.style.backgroundColor = color;
                            labelEl.textContent = groupVal;
                            block.appendChild(labelEl);
                        } else {
                            block.style.backgroundColor = product.color_hex || '#666';
                            const shortName = product.brand + (product.pack_size > 1 ? ' ' + product.pack_size + 'pk' : '');
                            labelEl.textContent = shortName;
                            block.appendChild(labelEl);
                            if (blockHeight > 25) {
                                const priceEl = document.createElement('div');
                                priceEl.className = 'product-price';
                                priceEl.textContent = cFmt(product.price);
                                block.appendChild(priceEl);
                            }
                        }

                        block.addEventListener('mouseenter', (e) => showTooltip(e, product, pos));
                        block.addEventListener('mousemove',  (e) => moveTooltip(e));
                        block.addEventListener('mouseleave', hideTooltip);

                        bayProductClip.appendChild(block);
                    }
                });
            });
        });

        // ── LAYER 3: Bay border overlay lines ──
        const borderW = 2;
        bays.forEach((bay, bayIdx) => {
            const meta = layout[bayIdx];
            if (!meta || !meta.bodyEl) return;

            const bayEl     = meta.bodyEl.parentElement;
            const bayRect   = bayEl.getBoundingClientRect();
            const bayLeftPx = bayRect.left - containerRect.left;
            const bayWPx    = bayRect.width;

            const prevBay     = bayIdx > 0 ? bays[bayIdx - 1] : null;
            const gluedToPrev = prevBay && prevBay.glued_right;

            if (!gluedToPrev) {
                const line = document.createElement('div');
                line.className = 'bay-border-line';
                line.style.left   = bayLeftPx + 'px';
                line.style.width  = borderW + 'px';
                line.style.height = '100%';
                borderOverlay.appendChild(line);
            }
            if (!bay.glued_right) {
                const line = document.createElement('div');
                line.className = 'bay-border-line';
                line.style.left   = (bayLeftPx + bayWPx - borderW) + 'px';
                line.style.width  = borderW + 'px';
                line.style.height = '100%';
                borderOverlay.appendChild(line);
            }
        });
    });
}
