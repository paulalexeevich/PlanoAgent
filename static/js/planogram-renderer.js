/* PLANOGRAM RENDERER — Dashboard visualization (uses shared BayRenderer)
 *
 * Two-layer architecture:
 *   1. Equipment layer — bay borders, shelves, labels (BayRenderer)
 *   2. Product layer   — product blocks as absolute overlay, NOT clipped
 *      by bay boundaries.  Cross-bay products visually span the border.
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
        gluedGap: 0,
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

    // ── LAYER 2: Products (absolute overlay spanning full planogram) ──
    const productLayer = document.createElement('div');
    productLayer.className = 'product-layer';
    container.appendChild(productLayer);

    // Calculate bay body offsets from known geometry
    // (getBoundingClientRect unreliable during same-frame render)
    const bayGapPx   = 4;
    const gluedGapPx = 0;
    const borderW    = 2;   // .br-bay border-width
    let cumulativeLeft = 0;

    bays.forEach((bay, bayIdx) => {
        const meta = layout[bayIdx];
        if (!meta) return;

        const prevBay     = bayIdx > 0 ? bays[bayIdx - 1] : null;
        const gluedToPrev = prevBay && prevBay.glued_right;

        if (bayIdx > 0) {
            cumulativeLeft += gluedToPrev ? gluedGapPx : bayGapPx;
        }

        const leftBorder = gluedToPrev ? 0 : borderW;
        const bodyLeftPx = cumulativeLeft + leftBorder;
        const headerH    = meta.bodyEl.previousElementSibling
            ? meta.bodyEl.previousElementSibling.offsetHeight : 33;
        const bodyTopPx  = headerH + borderW;

        bay.shelves.forEach((shelf) => {
            const sMeta = meta.shelves.find(s => s.shelf_number === shelf.shelf_number);
            if (!sMeta) return;

            const positions = shelf.positions || [];
            if (!positions.length) return;

            const shelfHeight = sMeta.heightPx;
            const shelfTopPx  = bodyTopPx + meta.bodyHPx - sMeta.bottomPx - sMeta.heightPx;

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
                    block.style.top    = shelfTopPx + (shelfHeight - blockHeight) + 'px';

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

                    productLayer.appendChild(block);
                }
            });
        });

        const rightBorder = bay.glued_right ? 0 : borderW;
        cumulativeLeft += leftBorder + meta.widthPx + rightBorder;
    });

    // ── LAYER 3: Bay border overlay lines (on top of products) ──
    const borderOverlay = document.createElement('div');
    borderOverlay.className = 'bay-border-overlay';
    container.appendChild(borderOverlay);

    let bdrLeft = 0;
    bays.forEach((bay, bayIdx) => {
        const meta = layout[bayIdx];
        if (!meta) return;

        const prevBay     = bayIdx > 0 ? bays[bayIdx - 1] : null;
        const gluedToPrev = prevBay && prevBay.glued_right;

        if (bayIdx > 0) {
            bdrLeft += gluedToPrev ? gluedGapPx : bayGapPx;
        }
        const lBorder = gluedToPrev ? 0 : borderW;
        const rBorder = bay.glued_right ? 0 : borderW;
        const bayTotalW = lBorder + meta.widthPx + rBorder;

        // Draw left and right vertical border lines for this bay
        if (lBorder > 0) {
            const line = document.createElement('div');
            line.className = 'bay-border-line';
            line.style.left   = bdrLeft + 'px';
            line.style.top    = '0';
            line.style.width  = borderW + 'px';
            line.style.height = '100%';
            borderOverlay.appendChild(line);
        }
        if (rBorder > 0) {
            const line = document.createElement('div');
            line.className = 'bay-border-line';
            line.style.left   = (bdrLeft + bayTotalW - borderW) + 'px';
            line.style.top    = '0';
            line.style.width  = borderW + 'px';
            line.style.height = '100%';
            borderOverlay.appendChild(line);
        }

        bdrLeft += bayTotalW;
    });
}
