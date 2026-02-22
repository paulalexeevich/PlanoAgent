/* PLANOGRAM RENDERER — Dashboard visualization (uses shared BayRenderer) */

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

    container.classList.toggle('show-dimensions', showDimensions);

    BayRenderer.render({
        container,
        scale,
        bayGap:   4,
        gluedGap: -2,
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

            shelf.positions.forEach((pos, posIdx) => {
                const product = productsMap[pos.product_id];
                if (!product) return;

                const singleWidth  = product.width_in * scale;
                const blockHeight  = Math.min(product.height_in * scale, shelfHeight - 4);
                const baseLeft     = pos.x_position * scale;

                for (let f = 0; f < pos.facings_wide; f++) {
                    const block = document.createElement('div');
                    block.className = 'product-block';
                    if (f > 0) block.classList.add('facing-repeat');
                    block.style.width  = singleWidth + 'px';
                    block.style.height = blockHeight + 'px';
                    block.style.left   = (baseLeft + f * singleWidth) + 'px';

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

