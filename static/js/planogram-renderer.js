/* PLANOGRAM RENDERER — Dashboard visualization (uses shared BayRenderer) */

function _buildCrossBayMap(equipment) {
    /**
     * Detect products that straddle adjacent glued bays on the same shelf row.
     * Returns a Set of keys "bayIdx:shelfNum:edge" where edge is "right" or "left".
     * Used to add CSS classes so cross-bay products render seamlessly.
     */
    const marks = new Set();
    const bays = equipment.bays || [];
    for (let i = 0; i < bays.length - 1; i++) {
        if (!bays[i].glued_right) continue;
        const bayA = bays[i], bayB = bays[i + 1];
        for (const shA of (bayA.shelves || [])) {
            for (const shB of (bayB.shelves || [])) {
                if (shA.shelf_number !== shB.shelf_number) continue;
                const posA = shA.positions || [];
                const posB = shB.positions || [];
                if (!posA.length || !posB.length) continue;
                const lastA  = posA[posA.length - 1];
                const firstB = posB[0];
                if (lastA.product_id === firstB.product_id) {
                    marks.add(i + ':' + shA.shelf_number + ':right');
                    marks.add((i + 1) + ':' + shB.shelf_number + ':left');
                }
            }
        }
    }
    return marks;
}

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

    const bays   = BayRenderer.normalizeDashboard(planogramData.equipment);
    const crossBay = _buildCrossBayMap(planogramData.equipment);

    container.classList.toggle('show-dimensions', showDimensions);

    BayRenderer.render({
        container,
        scale,
        bayGap:   4,
        gluedGap: 0,
        bays,

        onShelf(shelfEl, shelf, si, bay, bayIdx) {
            const hasProducts = shelf.positions && shelf.positions.length > 0;
            if (!hasProducts) {
                shelfEl.classList.add('empty-shelf');
                const emptyLabel = document.createElement('span');
                emptyLabel.className = 'empty-shelf-label';
                emptyLabel.textContent = 'Empty';
                shelfEl.appendChild(emptyLabel);
                return;
            }

            const shelfHeight = shelf.height_in * scale;
            const posCount = shelf.positions.length;

            const shelfWidthPx = bay.width_in * scale;

            shelf.positions.forEach((pos, posIdx) => {
                const product = productsMap[pos.product_id];
                if (!product) return;

                const singleWidth  = product.width_in * scale;
                const blockHeight  = Math.min(product.height_in * scale, shelfHeight - 4);
                const baseLeft     = pos.x_position * scale;

                const isLastPos  = posIdx === posCount - 1;
                const isFirstPos = posIdx === 0;
                const bridgeRight = isLastPos  && crossBay.has(bayIdx + ':' + shelf.shelf_number + ':right');
                const bridgeLeft  = isFirstPos && crossBay.has(bayIdx + ':' + shelf.shelf_number + ':left');

                for (let f = 0; f < pos.facings_wide; f++) {
                    const block = document.createElement('div');
                    block.className = 'product-block';
                    if (f > 0) block.classList.add('facing-repeat');

                    const isRightEdge = bridgeRight && f === pos.facings_wide - 1;
                    const isLeftEdge  = bridgeLeft  && f === 0;
                    if (isRightEdge) block.classList.add('cross-bay-right');
                    if (isLeftEdge)  block.classList.add('cross-bay-left');

                    const leftPx  = Math.floor(baseLeft + f * singleWidth);
                    let   rightPx = Math.floor(baseLeft + (f + 1) * singleWidth);

                    // Stretch last facing to fill remaining shelf space (no visual gap)
                    if (isLastPos && f === pos.facings_wide - 1) {
                        rightPx = Math.floor(shelfWidthPx);
                    }

                    block.style.width  = (rightPx - leftPx) + 'px';
                    block.style.height = blockHeight + 'px';
                    block.style.left   = leftPx + 'px';

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

                    shelfEl.appendChild(block);
                }
            });
        },
    });
}

