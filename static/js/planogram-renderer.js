/* PLANOGRAM RENDERER — Main visualization rendering */

function _addGroupBand(shelfEl, startX, width, segment, shelfHeight) {
    if (width <= 0) return;
    const color = SEGMENT_COLORS[segment] || SEGMENT_COLORS.Other;
    const band = document.createElement('div');
    band.className = 'group-band';
    band.style.left = startX + 'px';
    band.style.width = width + 'px';
    band.style.borderColor = color;
    band.style.backgroundColor = color;
    shelfEl.appendChild(band);
    const lbl = document.createElement('div');
    lbl.className = 'group-label-overlay';
    lbl.style.left = (startX + 2) + 'px';
    lbl.style.color = color;
    lbl.textContent = segment;
    shelfEl.appendChild(lbl);
}

function renderPlanogram() {
    const container = document.getElementById('planogramContainer');
    container.innerHTML = '';

    if (!planogramData || !planogramData.equipment) return;

    const equipment = planogramData.equipment;

    const isDtLayer = currentLayer.startsWith('dt-');
    const dtLevelIdx = isDtLayer ? parseInt(currentLayer.split('-')[1]) : -1;
    const dtLevel = isDtLayer && decisionTreeData && decisionTreeData.levels
        ? decisionTreeData.levels[dtLevelIdx] : null;
    const dtLevelName = dtLevel ? dtLevel.name : null;
    const dtPalette = dtLevelName ? buildDtPaletteForLevel(dtLevelName) : {};

    renderLayerLegend(dtLevelName, dtPalette);

    const segMap = (!isDtLayer) ? buildSegmentMap() : {};

    equipment.bays.forEach(bay => {
        const bayEl = document.createElement('div');
        bayEl.className = 'bay';
        bayEl.style.width = (bay.width_in * scale) + 'px';

        const header = document.createElement('div');
        header.className = 'bay-header';
        header.textContent = `Bay ${bay.bay_number}`;
        bayEl.appendChild(header);

        const body = document.createElement('div');
        body.className = 'bay-body';
        body.style.height = (bay.height_in * scale) + 'px';

        const sortedShelves = [...bay.shelves].sort((a, b) => a.y_position - b.y_position);

        sortedShelves.forEach((shelf) => {
            const hasProducts = shelf.positions && shelf.positions.length > 0;
            const shelfEl = document.createElement('div');
            shelfEl.className = 'shelf-row' + (!hasProducts ? ' empty-shelf' : '');

            const shelfHeight = shelf.height_in * scale;
            shelfEl.style.height = shelfHeight + 'px';
            shelfEl.style.width = bay.width_in * scale + 'px';
            shelfEl.style.position = 'absolute';
            shelfEl.style.bottom = (shelf.y_position * scale) + 'px';
            shelfEl.style.left = '0';

            const label = document.createElement('span');
            label.className = 'shelf-label';
            label.textContent = `S${shelf.shelf_number} — ${dFmt(shelf.height_in)}`;
            shelfEl.appendChild(label);

            if (!hasProducts) {
                const emptyLabel = document.createElement('span');
                emptyLabel.className = 'empty-shelf-label';
                emptyLabel.textContent = `Empty`;
                shelfEl.appendChild(emptyLabel);
            }

            if (hasProducts) {
                let currentSegment = null;
                let segStartX = 0;

                shelf.positions.forEach((pos, posIdx) => {
                    const product = productsMap[pos.product_id];
                    if (!product) return;

                    const blockWidth = product.width_in * pos.facings_wide * scale;
                    const blockHeight = Math.min(product.height_in * scale, shelfHeight - 4);

                    if (!isDtLayer) {
                        const seg = segMap[pos.product_id] || null;
                        if (seg && seg !== currentSegment) {
                            if (currentSegment) {
                                _addGroupBand(shelfEl, segStartX, pos.x_position * scale - segStartX, currentSegment, shelfHeight);
                            }
                            currentSegment = seg;
                            segStartX = pos.x_position * scale;
                        }
                        if (posIdx === shelf.positions.length - 1 && currentSegment) {
                            const endX = pos.x_position * scale + blockWidth;
                            _addGroupBand(shelfEl, segStartX, endX - segStartX, currentSegment, shelfHeight);
                        }
                    }

                    const block = document.createElement('div');
                    block.className = 'product-block';
                    block.style.width = blockWidth + 'px';
                    block.style.height = blockHeight + 'px';
                    block.style.left = (pos.x_position * scale) + 'px';

                    const labelEl = document.createElement('div');
                    labelEl.className = 'product-label';

                    if (isDtLayer && dtLevelName) {
                        const groups = dtPositionMap[pos.product_id];
                        const groupVal = groups ? (groups[dtLevelName] || '?') : '?';
                        const color = dtPalette[groupVal] || '#666';
                        block.style.backgroundColor = color;
                        labelEl.textContent = groupVal;
                        block.appendChild(labelEl);
                    } else {
                        block.style.backgroundColor = product.color_hex || '#666';
                        const shortName = product.brand + (product.pack_size > 1 ? ` ${product.pack_size}pk` : '');
                        labelEl.textContent = shortName;
                        block.appendChild(labelEl);
                        if (blockHeight > 25) {
                            const priceEl = document.createElement('div');
                            priceEl.className = 'product-price';
                            priceEl.textContent = '$' + product.price.toFixed(2);
                            block.appendChild(priceEl);
                        }
                    }

                    if (pos.facings_wide > 1) {
                        const badge = document.createElement('div');
                        badge.className = 'facing-badge';
                        badge.textContent = pos.facings_wide + 'x';
                        block.appendChild(badge);
                    }

                    block.addEventListener('mouseenter', (e) => showTooltip(e, product, pos));
                    block.addEventListener('mousemove', (e) => moveTooltip(e));
                    block.addEventListener('mouseleave', hideTooltip);

                    shelfEl.appendChild(block);
                });
            }

            body.appendChild(shelfEl);
        });

        bayEl.appendChild(body);

        const footer = document.createElement('div');
        footer.className = 'bay-footer';
        footer.textContent = dFmt(bay.width_in);
        bayEl.appendChild(footer);

        container.appendChild(bayEl);
    });
}

function buildSegmentMap() {
    if (!complianceData || !complianceData.position_groups) return {};
    const map = {};
    complianceData.position_groups.forEach(pg => {
        if (pg.groups && pg.groups.Segment) {
            map[pg.product_id] = pg.groups.Segment;
        }
    });
    return map;
}
