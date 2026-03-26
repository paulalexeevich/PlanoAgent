(function() {
    'use strict';

    // Store last rendered bay data so we can re-scale on zoom
    let _lastRenderedBays = null;

    // Hook into the zoom/re-render cycle alongside renderAllMiniPlanograms
    const _origSchedule = window.scheduleReRenderPlanograms;
    window.scheduleReRenderPlanograms = function() {
        if (_origSchedule) _origSchedule();
        if (_lastRenderedBays) {
            setTimeout(_reApplyProposedWidths, 150);  // slightly after plano re-render
        }
    };

    function _reApplyProposedWidths() {
        if (!_lastRenderedBays) return;
        const photoNames = (typeof PV !== 'undefined' && PV.photos) || [];
        for (const bay of _lastRenderedBays) {
            const photoName = photoNames[bay.bay_number - 1];
            const card = photoName ? document.getElementById('card-' + photoName) : null;
            if (!card) continue;
            const imgEl = document.getElementById('img-' + photoName);
            const photoDisplayW = imgEl ? (imgEl.offsetWidth || imgEl.clientWidth) : 0;
            if (photoDisplayW < 20) continue;
            const totalCm = bay.width_cm || 120;
            const pxPerCm = photoDisplayW / totalCm;
            const realoBar = (typeof PV !== 'undefined' && PV.recog && PV.recog.bayMap)
                ? PV.recog.bayMap[photoName] : null;
            const bayWidthIn = realoBar ? (realoBar.width_in || 49.21) : 49.21;
            const sc = photoDisplayW / bayWidthIn;
            const section = card.querySelector('.proposed-bay-section');
            if (!section) continue;
            const shelvesCont = section.querySelector('.pp-shelves');
            if (shelvesCont) shelvesCont.style.width = photoDisplayW + 'px';
            section.querySelectorAll('.pp-shelf-bar').forEach(bar => {
                bar.style.width = photoDisplayW + 'px';
                const heightIn = parseFloat(bar.dataset.heightIn) || 0;
                if (heightIn > 0) bar.style.height = Math.round(heightIn * sc) + 'px';
                bar.querySelectorAll('.pprod').forEach(block => {
                    const cmW = parseFloat(block.dataset.widthCm) || 0;
                    block.style.width = Math.max(2, cmW * pxPerCm) + 'px';
                });
            });
        }
    }

    const btn = document.getElementById('btnProposedPlanogram');
    const lblEl = document.getElementById('proposedLabel');
    const spinEl = document.getElementById('proposedSpinner');
    const resultEl = document.getElementById('proposedResult');
    const statsEl = document.getElementById('proposedStats');
    const legendEl = document.getElementById('proposedLegend');

    if (!btn) return;

    btn.addEventListener('click', async () => {
        btn.disabled = true;
        lblEl.textContent = 'Running optimization…';
        spinEl.style.display = '';
        resultEl.innerHTML = '';
        statsEl.style.display = 'none';
        legendEl.style.display = 'none';

        try {
            const resp = await fetch('/api/actions/proposed-planogram');
            const data = await resp.json();

            spinEl.style.display = 'none';

            if (data.status !== 'success') {
                resultEl.innerHTML = `<div class="training-error">${data.error || 'Unknown error'}</div>`;
                lblEl.textContent = 'Retry';
                btn.disabled = false;
                return;
            }

            const s = data.summary || {};
            resultEl.innerHTML =
                `<div class="training-success">Optimization complete — strategy: <strong>${data.strategy}</strong></div>`;

            const followsDT = s.follows_dt_count || 0;
            const violatesDT = s.violates_dt_count || 0;
            const placed = s.placed_count || 0;
            const opportunisticAdded = s.opportunistic_added_count || 0;
            const treePct = (s.tree_compliance_pct || 0).toFixed(0);
            const treeMax = s.tree_score_max || 3;
            const treeDepth = (s.tree_depth_levels || []).join(' > ') || 'category_l1 > category_l2 > brand';
            const treeTooltip = `Tree compliance: sum of scores / (placed × ${treeMax}) × 100\nScore per product: depth of common tree prefix (0..${treeMax})\nDepth keys: ${treeDepth}\nFollows DT: ${followsDT}, Violates: ${violatesDT}`;
            statsEl.innerHTML = `
                <div class="pp-stat-row">
                    <span>Score: <strong>${((data.combined_score || 0) * 100).toFixed(0)}%</strong></span>
                    <span>Installed: <strong>${placed} / ${s.total_out_of_shelf || 0}</strong></span>
                    ${opportunisticAdded > 0 ? `<span>Opportunistic: <strong>${opportunisticAdded}</strong></span>` : ''}
                    <span>Time: <strong>${(s.total_time_min || 0).toFixed(0)} min</strong></span>
                    <span title="${treeTooltip}" style="cursor:help">Tree: <strong>${treePct}%</strong> <span style="font-size:9px;color:var(--text-secondary)">(${followsDT} ok / ${violatesDT} break)</span></span>
                </div>
            `;
            statsEl.style.display = '';
            // Legend is now shown inline in each bay header — hide the side-panel legend
            legendEl.style.display = 'none';

            _renderProposedBays(data);
            _renderActionsList(data);

            lblEl.textContent = 'Reload';
            btn.disabled = false;

            document.getElementById('step4Indicator').classList.add('completed');
            document.getElementById('trainStep4').classList.add('completed');
            if (typeof enableStepCollapse === 'function') enableStepCollapse(4);
        } catch (e) {
            spinEl.style.display = 'none';
            resultEl.innerHTML = `<div class="training-error">Failed: ${e.message}</div>`;
            lblEl.textContent = 'Retry';
            btn.disabled = false;
            console.error('[proposed-planogram]', e);
        }
    });

    function _renderProposedBays(data) {
        const bays = data.bays || [];
        if (!bays.length) return;
        _lastRenderedBays = bays;

        // Shared tooltip
        let tooltip = document.getElementById('ppTooltip');
        if (!tooltip) {
            tooltip = document.createElement('div');
            tooltip.id = 'ppTooltip';
            tooltip.className = 'pp-tooltip';
            document.body.appendChild(tooltip);
        }

        // Product image fallback from PV planogramFacings
        const facingsMap = (typeof PV !== 'undefined' && PV.planogramFacings) || {};

        // Map bay_number → photo card using PV.photos order (bay 1 = photos[0], etc.)
        const photoNames = (typeof PV !== 'undefined' && PV.photos) || [];

        for (const bay of bays) {
            const photoName = photoNames[bay.bay_number - 1];
            const card = photoName ? document.getElementById('card-' + photoName) : null;

            // Remove old proposed section for this bay if re-running
            if (card) {
                const old = card.querySelector('.proposed-bay-section');
                if (old) old.remove();
            }

            // Build the proposed bay section
            const section = document.createElement('div');
            section.className = 'proposed-bay-section';

            const secHeader = document.createElement('div');
            secHeader.className = 'plano-bay-header proposed-bay-header';
            secHeader.innerHTML = `<span>Proposed Planogram</span>`;
            section.appendChild(secHeader);

            // Outer scroll wrapper — same pattern as .plano-mini
            const scrollWrap = document.createElement('div');
            scrollWrap.className = 'pp-scroll-wrap';

            const shelvesCont = document.createElement('div');
            shelvesCont.className = 'pp-shelves';
            scrollWrap.appendChild(shelvesCont);
            section.appendChild(scrollWrap);

            // Highest shelf_number = top physical shelf
            const sorted = [...(bay.shelves || [])].sort(
                (a, b) => b.shelf_number - a.shelf_number
            );

            const totalCm = bay.width_cm || 120;

            // Look up realogram bay for shelf heights (set in Step 2)
            const realoBar = (typeof PV !== 'undefined' && PV.recog && PV.recog.bayMap)
                ? PV.recog.bayMap[photoName] : null;
            const realoShelfMap = {};
            if (realoBar) {
                realoBar.shelves.forEach(s => { realoShelfMap[s.shelf_number] = s; });
            }
            const bayWidthIn = realoBar ? (realoBar.width_in || 49.21) : 49.21;

            // Build all shelf rows (widths & heights set in px after layout)
            const shelfBars = [];  // collect bars for resizing

            for (const shelf of sorted) {
                // No separate label column — label goes inside bar (matches br-shelf-label style)
                const bar = document.createElement('div');
                bar.className = 'pp-shelf-bar';
                bar.dataset.shelfNum = shelf.shelf_number;

                // Height will be applied after layout using same scale as realogram
                const realoShelf = realoShelfMap[shelf.shelf_number];
                if (realoShelf) {
                    bar.dataset.heightIn = realoShelf.height_in;
                }

                // Shelf number label inside bar (matches "S4 — 30 cm" style)
                const lbl = document.createElement('span');
                lbl.className = 'br-shelf-label pp-shelf-label-inner';
                const heightCm = realoShelf ? Math.round(realoShelf.height_in * 2.54) : '';
                lbl.textContent = `S${shelf.shelf_number}` + (heightCm ? ` — ${heightCm} cm` : '');
                bar.appendChild(lbl);

                shelfBars.push({ bar, shelf });

                for (const prod of (shelf.products || [])) {
                    const block = document.createElement('div');
                    block.className = 'pprod';
                    if (prod.change_type === 'new') block.classList.add('is-new');
                    else if (prod.change_type === 'reduced') block.classList.add('is-reduced');
                    // Store cm width as data attribute; pixel width applied after layout
                    block.dataset.widthCm = prod.total_width_cm;

                    // Product image — same lookup chain as the realogram renderer:
                    // 1. recognition_id → PV.recog.productsMap → image_no_bg_url || image_url
                    // 2. image_url from API (no-bg from product map)
                    // 3. planogramFacings fallback
                    const recogProduct = (prod.recognition_id && typeof PV !== 'undefined'
                        && PV.recog && PV.recog.productsMap)
                        ? PV.recog.productsMap[prod.recognition_id] : null;
                    const planoInfo = facingsMap[prod.tiny_name] || {};
                    const imageUrl = (recogProduct && (recogProduct.image_no_bg_url || recogProduct.image_url))
                        || prod.image_no_bg_url
                        || prod.image_url
                        || planoInfo.image_no_bg_url
                        || planoInfo.image_url
                        || null;

                    if (imageUrl) {
                        const facingCount = Math.min(prod.facings, 6);
                        for (let f = 0; f < facingCount; f++) {
                            const img = document.createElement('img');
                            img.src = imageUrl;
                            img.className = 'pprod-img';
                            img.alt = prod.tiny_name;
                            img.loading = 'lazy';
                            img.onerror = () => { img.style.display = 'none'; };
                            block.appendChild(img);
                        }
                    } else {
                        block.style.backgroundColor = prod.color || '#6b7280';
                        const lb = document.createElement('div');
                        lb.className = 'pprod-label';
                        lb.textContent = prod.tiny_name || prod.product_code;
                        block.appendChild(lb);
                    }

                    // Change badge
                    if (prod.change_type !== 'existing') {
                        const overlay = document.createElement('div');
                        overlay.className = 'pprod-overlay';
                        overlay.textContent = prod.change_type === 'new' ? '＋' :
                            `${prod.reduced_from}→${prod.facings}`;
                        block.appendChild(overlay);
                    }

                    // Tooltip
                    block.addEventListener('mouseenter', (e) => {
                        let changeHtml = '';
                        if (prod.change_type === 'new')
                            changeHtml = '<span class="tt-tag tt-new">New installation</span>';
                        else if (prod.change_type === 'reduced')
                            changeHtml = `<span class="tt-tag tt-reduced">Reduced: ${prod.reduced_from} → ${prod.facings}</span>`;
                        else
                            changeHtml = '<span class="tt-tag tt-existing">Unchanged</span>';
                        const ttImg = (recogProduct && (recogProduct.image_no_bg_url || recogProduct.image_url))
                            || prod.image_no_bg_url || prod.image_url
                            || planoInfo.image_no_bg_url || planoInfo.image_url || null;
                        const imgHtml = ttImg ? `<img src="${ttImg}" class="tt-img" alt="">` : '';
                        const displayName = prod.product_name || prod.tiny_name || prod.product_code;
                        const codeHtml = prod.tiny_name && prod.tiny_name !== displayName
                            ? `<div class="tt-code">${prod.tiny_name}</div>` : '';
                        tooltip.innerHTML = `
                            ${imgHtml}
                            <div class="tt-name">${displayName}</div>
                            ${codeHtml}
                            <div class="tt-change">${changeHtml}</div>
                            <div class="tt-row">Facings: <strong>${prod.facings}</strong> × ${prod.width_cm} cm = <strong>${prod.total_width_cm} cm</strong></div>
                            ${prod.avg_sale_amount ? `<div class="tt-row">Avg sale: <strong>₽${prod.avg_sale_amount.toFixed(0)}</strong></div>` : ''}
                            ${prod.brand_name ? `<div class="tt-row">Brand: ${prod.brand_name}</div>` : ''}
                        `;
                        tooltip.style.display = 'block';
                        _posTooltip(e);
                    });
                    block.addEventListener('mousemove', _posTooltip);
                    block.addEventListener('mouseleave', () => { tooltip.style.display = 'none'; });

                    bar.appendChild(block);
                }

                shelvesCont.appendChild(bar);
            }

            // Inject into the matching photo card after its plano-bay-section
            if (card) {
                const planoBaySection = card.querySelector('.plano-bay-section');
                if (planoBaySection) {
                    planoBaySection.after(section);
                } else {
                    card.appendChild(section);
                }

                // Apply pixel widths + heights after layout using same scale as BayRenderer
                requestAnimationFrame(() => {
                    const imgEl = photoName ? document.getElementById('img-' + photoName) : null;
                    const photoDisplayW = imgEl ? (imgEl.offsetWidth || imgEl.clientWidth) : 0;
                    if (photoDisplayW > 20) {
                        const pxPerCm = photoDisplayW / totalCm;
                        // Same scale as BayRenderer: pixels per inch
                        const sc = photoDisplayW / bayWidthIn;
                        shelvesCont.style.width = photoDisplayW + 'px';
                        shelfBars.forEach(({ bar }) => {
                            bar.style.width = photoDisplayW + 'px';
                            // Match shelf height to realogram
                            const heightIn = parseFloat(bar.dataset.heightIn) || 0;
                            if (heightIn > 0) {
                                bar.style.height = Math.round(heightIn * sc) + 'px';
                            }
                            bar.querySelectorAll('.pprod').forEach(block => {
                                const cmW = parseFloat(block.dataset.widthCm) || 0;
                                block.style.width = Math.max(2, cmW * pxPerCm) + 'px';
                            });
                        });
                    }
                });
            }
        }

        // Scroll the first card into view
        const firstCard = document.querySelector('.photo-card');
        if (firstCard) firstCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function _renderActionsList(data) {
        const actions = data.actions || [];
        const s = data.summary || {};

        // Find or create the actions list container below proposedStats
        let listEl = document.getElementById('proposedActionsList');
        if (!listEl) {
            listEl = document.createElement('div');
            listEl.id = 'proposedActionsList';
            listEl.className = 'proposed-actions-list';
            // Insert after statsEl
            statsEl.after(listEl);
        }

        if (!actions.length) { listEl.style.display = 'none'; return; }

        const installed = actions.filter(a => a.installed);
        const skipped = actions.filter(a => !a.installed);
        const totalLostSales = skipped.reduce((sum, a) => sum + (a.avg_sale_amount || 0), 0);

        listEl.innerHTML = `
            <div class="pal-header">
                <span class="pal-title">Out-of-Shelf Actions</span>
                <span class="pal-counts">
                    <span class="pal-installed">${installed.length} installed</span>
                    <span class="pal-skipped">${skipped.length} skipped</span>
                </span>
            </div>
            ${totalLostSales > 0 ? `<div class="pal-lost-sales">Remaining lost sales: <strong>${Math.round(totalLostSales).toLocaleString('ru-RU')} ₽/wk</strong></div>` : ''}
            <div class="pal-items">
                ${actions.map((a, i) => {
                    const priClass = a.priority === 'high' ? 'apri-high' : a.priority === 'medium' ? 'apri-med' : 'apri-low';
                    const sale = a.avg_sale_amount || 0;
                    const locationHtml = a.installed
                        ? `<span class="pal-location">${a.actual_shelf}${a.planogram_shelf && a.planogram_shelf !== a.actual_shelf ? ` <span class="pal-shifted">(planogram: ${a.planogram_shelf})</span>` : ''}</span>`
                        : `<span class="pal-reason">${a.reason || 'No space'}</span>`;
                    const sourceHtml = a.installed && a.space_source === 'excess_facings'
                        ? `<span class="pal-source-tag">via reduction</span>` : '';
                    const opportunisticHtml = a.installed && a.opportunistic
                        ? `<span class="pal-source-tag">opportunistic</span>` : '';
                    const reductionsHtml = (a.reductions && a.reductions.length)
                        ? `<div class="pal-reductions">Reduced: ${a.reductions.map(r =>
                            `<span class="pal-red-item" title="${r.product_code}">${r.tiny_name || r.product_code} ${r.reduce_from}→${r.reduce_to}</span>`
                          ).join(', ')}</div>` : '';
                    const timeHtml = a.installed && a.time_min
                        ? `<span class="pal-time">${a.time_min} min</span>` : '';

                    // Tree score badge
                    let treeHtml = '';
                    if (a.installed && a.tree_score !== null && a.tree_score !== undefined) {
                        const ts = a.tree_score;
                        const tsMax = a.tree_score_max || 3;
                        const tsClass = ts >= 4 ? 'tree-perfect' : ts >= 1 ? 'tree-ok' : 'tree-break';
                        const tsLabel = '●'.repeat(Math.max(0, ts)) + '○'.repeat(Math.max(0, tsMax - ts));
                        const tsText = ts === tsMax ? 'Exact' : ts > 0 ? `Depth ${ts}` : 'Break';
                        treeHtml = `
                            <div class="pal-tree ${tsClass}" title="${a.tree_reason}\nShelf had: ${a.shelf_groups_before}\nProduct: ${a.tree_group}">
                                <span class="tree-dots">${tsLabel}</span>
                                <span class="tree-label">${tsText}</span>
                                <span class="tree-score-num">${ts}/${tsMax}</span>
                            </div>`;
                    }

                    return `
                        <div class="pal-item ${a.installed ? 'pal-item-installed' : 'pal-item-skipped'} ${priClass}">
                            <div class="pal-rank">${i + 1}</div>
                            <div class="pal-body">
                                <div class="pal-name">${a.product_name || a.tiny_name}</div>
                                <div class="pal-meta">
                                    ${a.brand ? `<span class="tag-brand">${a.brand}</span>` : ''}
                                    ${a.installed && a.install_facings > 1 ? `<span class="pal-facings">${a.install_facings} facings</span>` : ''}
                                    ${sale > 0 ? `<span class="pal-sale">${sale.toLocaleString('ru-RU', {maximumFractionDigits:0})} ₽/wk</span>` : ''}
                                    ${timeHtml}${sourceHtml}${opportunisticHtml}
                                </div>
                                <div class="pal-where">${locationHtml}</div>
                                ${reductionsHtml}
                                ${treeHtml}
                            </div>
                            <div class="pal-status ${a.installed ? 'pal-ok' : 'pal-no'}">
                                ${a.installed ? '✓' : '✗'}
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
        listEl.style.display = '';
    }

    function _posTooltip(e) {
        const tt = document.getElementById('ppTooltip');
        if (!tt) return;
        const vw = window.innerWidth, vh = window.innerHeight;
        let x = e.clientX + 14, y = e.clientY - 10;
        if (x + 260 > vw) x = e.clientX - 274;
        if (y + 160 > vh) y = e.clientY - 160;
        tt.style.left = x + 'px';
        tt.style.top = y + 'px';
    }

    // Unlock step 4 when step 3 completes (step3Indicator gets class "completed")
    function unlockStep4() {
        document.getElementById('trainStep4').classList.remove('locked');
        document.getElementById('trainStep4').classList.add('active');
        btn.disabled = false;
        var s4ind = document.getElementById('step4Indicator');
        if (s4ind) s4ind.classList.add('active');
    }

    var step3Ind = document.getElementById('step3Indicator');
    if (step3Ind) {
        // Already completed (page reload after build)?
        if (step3Ind.classList.contains('completed')) {
            unlockStep4();
        } else {
            var obs = new MutationObserver(function() {
                if (step3Ind.classList.contains('completed')) {
                    unlockStep4();
                    obs.disconnect();
                }
            });
            obs.observe(step3Ind, { attributes: true, attributeFilter: ['class'] });
        }
    }
})();
