/* PLANOGRAM RENDERER — Dashboard visualization (uses shared BayRenderer)
 *
 * Three-layer architecture:
 *   1. Equipment layer — bay borders, shelves, labels (BayRenderer)
 *   2. Product layer   — product blocks as absolute overlay, NOT clipped
 *      by bay boundaries.  Cross-bay products visually span the border
 *      ONLY when shelves are physically aligned.  Misaligned bay boundaries
 *      never have cross-bay products (the algorithm prevents it).
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

    const productLayer = document.createElement('div');
    productLayer.className = 'product-layer';
    container.appendChild(productLayer);

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
            const bodyHPx    = bodyRect.height;

            bay.shelves.forEach((shelf) => {
                const sMeta = meta.shelves.find(s => s.shelf_number === shelf.shelf_number);
                if (!sMeta || !sMeta.el) return;

                const positions = shelf.positions || [];
                if (!positions.length) return;

                const shelfRect   = sMeta.el.getBoundingClientRect();
                const shelfTopPx  = shelfRect.top  - containerRect.top;
                const shelfHeight = shelfRect.height;

                positions.forEach((pos) => {
                    if (pos._phantom) return;

                    const product = productsMap[pos.product_id];
                    if (!product) return;

                    const singleWidth = product.width_in * scale;
                    const blockHeight = Math.min(product.height_in * scale, shelfHeight - 4);
                    const baseLeft    = pos.x_position * scale;

                    for (let f = 0; f < pos.facings_wide; f++) {
                        const block = document.createElement('div');
                        block.className = 'product-block';
                        if (f > 0) block.classList.add('facing-repeat');

                        const leftPx  = bodyLeftPx + baseLeft + f * singleWidth;
                        const widthPx = singleWidth;

                        block.style.width  = widthPx + 'px';
                        block.style.height = blockHeight + 'px';
                        block.style.left   = leftPx + 'px';
                        block.style.top    = (shelfTopPx + shelfHeight - blockHeight) + 'px';

                        if (isDtLayer && dtLevelName) {
                            const groups   = dtPositionMap[pos.product_id];
                            const groupVal = groups ? (groups[dtLevelName] || '?') : '?';
                            const color    = dtPalette[groupVal] || '#666';
                            block.style.backgroundColor = color;
                            const labelEl = document.createElement('div');
                            labelEl.className = 'product-label';
                            labelEl.textContent = groupVal;
                            block.appendChild(labelEl);
                        } else {
                            const hasNoBg = !!product.image_no_bg_url;
                            const imgSrc = product.image_no_bg_url || product.image_url;

                            if (imgSrc && blockHeight > 14 && widthPx > 10) {
                                block.classList.add('product-block-image');
                                if (hasNoBg) {
                                    block.classList.add('product-no-bg');
                                }
                                const imgEl = document.createElement('img');
                                imgEl.src = imgSrc;
                                imgEl.className = 'product-image';
                                imgEl.alt = product.name || '';
                                imgEl.draggable = false;
                                block.appendChild(imgEl);
                            } else {
                                block.style.backgroundColor = product.color_hex || '#666';
                            }
                        }

                        block.addEventListener('mouseenter', (e) => showTooltip(e, product, pos));
                        block.addEventListener('mousemove',  (e) => moveTooltip(e));
                        block.addEventListener('mouseleave', hideTooltip);

                        productLayer.appendChild(block);
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
