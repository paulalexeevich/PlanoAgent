/* Training 3 — Realogram vs Planogram Comparison
 * Displays realogram (from recognition) on top and planogram (planned layout) below.
 */

(function() {
    'use strict';

    // Store planogram data separately from realogram
    var planogramLayout = null;
    var comparisonData = null;

    // ── INITIALIZATION ─────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', function() {
        PV.photos = _PHOTOS_INIT || [];
        rebuildPhotoSelect();

        // Tab switching
        document.querySelectorAll('.side-panel-tab').forEach(function(tab) {
            tab.addEventListener('click', function() {
                var target = tab.dataset.tab;
                document.querySelectorAll('.side-panel-tab').forEach(function(t) {
                    t.classList.toggle('active', t.dataset.tab === target);
                });
                document.getElementById('tabCompare').style.display = target === 'compare' ? '' : 'none';
                document.getElementById('tabAnalytics').style.display = target === 'analytics' ? '' : 'none';
            });
        });

        // Side panel toggle
        document.querySelector('.side-panel-close').addEventListener('click', function() {
            document.getElementById('sidePanel').classList.toggle('open');
        });

        // Settings dropdown
        var settingsBtn = document.querySelector('.settings-btn');
        var settingsMenu = document.getElementById('settingsMenu');
        settingsBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            settingsMenu.classList.toggle('open');
        });
        document.addEventListener('click', function() {
            settingsMenu.classList.remove('open');
        });

        // View mode toggle
        document.getElementById('viewModeToggle').addEventListener('click', function(e) {
            if (e.target.tagName === 'BUTTON') {
                setView(e.target.dataset.view, e.target);
            }
        });

        document.getElementById('photoSelect').addEventListener('change', function(e) {
            loadSinglePhoto(e.target.value);
        });

        // Zoom controls
        document.querySelectorAll('.zoom-controls button').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var action = btn.dataset.action;
                if (action === 'zoom-in') zoomIn();
                else if (action === 'zoom-out') zoomOut();
                else if (action === 'zoom-fit') zoomFitAll();
            });
        });

        // Display layer toggles
        document.getElementById('showProducts').addEventListener('change', function(e) {
            document.querySelectorAll('.product-layer, .bbox-product').forEach(function(el) {
                el.style.display = e.target.checked ? '' : 'none';
            });
        });
        document.getElementById('showShelves').addEventListener('change', function(e) {
            document.querySelectorAll('.bbox-shelf').forEach(function(el) {
                el.style.display = e.target.checked ? '' : 'none';
            });
        });
        document.getElementById('showLabels').addEventListener('change', function(e) {
            document.querySelectorAll('.bbox-label').forEach(function(el) {
                el.style.display = e.target.checked ? '' : 'none';
            });
        });

        // Load initial data
        loadAllPhotos();

        // Load planogram facings for comparison
        loadPlanogramFacings();
    });

    // ── LOAD PLANOGRAM FACINGS ─────────────────────────────────────
    function loadPlanogramFacings() {
        fetch('/api/planogram-facings')
            .then(function(r) { return r.json(); })
            .then(function(facings) {
                PV.planogramFacings = facings || {};
                console.log('[training3] Loaded planogram facings:', Object.keys(facings).length);
            })
            .catch(function(err) {
                console.error('[training3] Failed to load planogram facings:', err);
                PV.planogramFacings = {};
            });
    }

    // ── OVERRIDE buildGrid TO SHOW DUAL PLANOGRAMS ─────────────────
    window.buildGrid = function(photoNames) {
        var grid = document.getElementById('photosGrid');
        grid.innerHTML = '';
        var loadedCount = 0;

        photoNames.forEach(function(name) {
            var card = document.createElement('div');
            card.className = 'photo-card';
            card.id = 'card-' + name;
            card.innerHTML =
                '<div class="photo-header">' +
                    '<span class="photo-title">' + name + '</span>' +
                '</div>' +
                '<div class="canvas-inner" id="canvas-' + name + '">' +
                    '<img id="img-' + name + '" alt="' + name + '">' +
                    '<svg id="svg-' + name + '" xmlns="http://www.w3.org/2000/svg"></svg>' +
                '</div>' +
                '<div class="dual-plano-container">' +
                    '<div class="plano-section">' +
                        '<div class="plano-section-header realogram">' +
                            '<span class="section-badge">Actual</span>' +
                            '<span>Realogram</span>' +
                        '</div>' +
                        '<div class="planogram-container plano-mini show-dimensions" id="realogram-' + name + '">' +
                            '<div class="plano-loading">Loading realogram...</div>' +
                        '</div>' +
                    '</div>' +
                    '<div class="plano-section">' +
                        '<div class="plano-section-header planogram">' +
                            '<span class="section-badge">Planned</span>' +
                            '<span>Planogram</span>' +
                        '</div>' +
                        '<div class="planogram-container plano-mini show-dimensions" id="planogram-' + name + '">' +
                            '<div class="plano-loading">Loading planogram...</div>' +
                        '</div>' +
                    '</div>' +
                '</div>';
            grid.appendChild(card);

            var img = document.getElementById('img-' + name);
            img.onload = function() {
                PV.naturalSizes[name] = { w: img.naturalWidth, h: img.naturalHeight };
                fetchPhotoData(name);
                loadedCount++;
                if (loadedCount === photoNames.length) {
                    setTimeout(zoomFitAll, 50);
                    fetchAndRenderDualPlanograms();
                }
            };
            img.src = '/demo-images/' + name + '.jpg';
        });
    };

    // ── FETCH AND RENDER BOTH REALOGRAM AND PLANOGRAM ──────────────
    function fetchAndRenderDualPlanograms() {
        // First load realogram (from recognition/saved)
        fetch('/api/realogram/load')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.status === 'success' && data.planogram) {
                    console.log('[training3] Loaded pre-saved realogram');
                    applyRealogramData(data);
                } else {
                    console.log('[training3] No saved realogram, building from recognition...');
                    return fetch('/api/build-from-recognition', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: '{}'
                    })
                    .then(function(r) { return r.json(); })
                    .then(function(fallback) {
                        if (fallback.status === 'success' && fallback.planogram) {
                            applyRealogramData(fallback);
                        }
                    });
                }
            })
            .catch(function(err) {
                console.error('[training3] Error loading realogram:', err);
            });

        // Then load planogram (the planned layout)
        fetch('/api/planogram?mode=coffee')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.planogram) {
                    console.log('[training3] Loaded planogram');
                    planogramLayout = data.planogram;
                    renderAllPlanograms();
                    runComparison();
                } else {
                    console.warn('[training3] No planogram data in response');
                    showPlanogramNotAvailable();
                }
            })
            .catch(function(err) {
                console.error('[training3] Error loading planogram:', err);
                showPlanogramNotAvailable();
            });
    }

    function applyRealogramData(data) {
        PV.recog.planogramData = data.planogram;
        PV.recog.productsMap = {};
        (PV.recog.planogramData.products || []).forEach(function(p) {
            PV.recog.productsMap[p.id] = p;
        });

        var bays = PV.recog.planogramData.equipment.bays || [];
        var sortedPhotos = PV.photos.slice().sort();
        PV.recog.bayMap = {};
        bays.forEach(function(bay, idx) {
            var photoName = sortedPhotos[idx];
            if (photoName) PV.recog.bayMap[photoName] = bay;
        });

        zoomFitAll();
        renderAllRealograms();
        runComparison();
    }

    // ── RENDER REALOGRAMS ──────────────────────────────────────────
    function renderAllRealograms() {
        if (!PV.recog.planogramData || !PV.recog.planogramData.equipment) return;

        Object.keys(PV.recog.bayMap).forEach(function(photoName) {
            var container = document.getElementById('realogram-' + photoName);
            if (!container) return;
            renderMiniBay(container, PV.recog.bayMap[photoName], photoName, 'realogram');
        });
    }

    // ── RENDER PLANOGRAMS ──────────────────────────────────────────
    function renderAllPlanograms() {
        if (!planogramLayout || !planogramLayout.equipment) {
            showPlanogramNotAvailable();
            return;
        }

        var bays = planogramLayout.equipment.bays || [];
        var sortedPhotos = PV.photos.slice().sort();

        sortedPhotos.forEach(function(photoName, idx) {
            var container = document.getElementById('planogram-' + photoName);
            if (!container) return;

            var bay = bays[idx];
            if (bay) {
                renderMiniBayPlanogram(container, bay, photoName);
            } else {
                container.innerHTML = '<div class="plano-empty-state">No planogram data for this bay</div>';
            }
        });
    }

    function showPlanogramNotAvailable() {
        PV.photos.forEach(function(photoName) {
            var container = document.getElementById('planogram-' + photoName);
            if (container) {
                container.innerHTML = '<div class="plano-empty-state">Planogram data not available</div>';
            }
        });
    }

    // ── RENDER SINGLE BAY (for realogram) ──────────────────────────
    function renderMiniBay(container, bay, photoName, type) {
        container.innerHTML = '';
        container.dataset.bayNumber = bay.bay_number;
        var bayWidthIn = bay.width_in || 49.21;
        var sc = getPlanoScaleForPhoto(photoName, bayWidthIn);

        var bays = BayRenderer.normalizeDashboard({ bays: [bay] });
        var layout = BayRenderer.render({
            container: container,
            scale: sc,
            bayGap: 0,
            gluedGap: 0,
            bays: bays,
            onShelf: function(shelfEl, shelf, si, bayObj, bayIdx) {
                shelfEl.dataset.shelfNumber = shelf.shelf_number;
                var hasProducts = shelf.positions && shelf.positions.length > 0;
                if (!hasProducts) {
                    shelfEl.classList.add('empty-shelf');
                    var lbl = document.createElement('span');
                    lbl.className = 'empty-shelf-label';
                    lbl.textContent = 'Empty';
                    shelfEl.appendChild(lbl);
                }
            }
        });

        if (!layout || !layout.length) return;

        var productLayer = document.createElement('div');
        productLayer.className = 'product-layer';
        container.appendChild(productLayer);

        requestAnimationFrame(function() {
            var containerRect = container.getBoundingClientRect();
            var meta = layout[0];
            if (!meta || !meta.bodyEl) return;

            bays[0].shelves.forEach(function(shelf) {
                var sMeta = meta.shelves.find(function(s) { return s.shelf_number === shelf.shelf_number; });
                if (!sMeta || !sMeta.el) return;
                var positions = shelf.positions || [];
                if (!positions.length) return;

                var shelfRect = sMeta.el.getBoundingClientRect();
                var shelfTopPx = shelfRect.top - containerRect.top;
                var shelfHeight = shelfRect.height;
                var bodyRect = meta.bodyEl.getBoundingClientRect();
                var bodyLeftPx = bodyRect.left - containerRect.left;

                positions.forEach(function(pos) {
                    if (pos._phantom) return;
                    var product = PV.recog.productsMap[pos.product_id];
                    if (!product) return;

                    var singleWidth = product.width_in * sc;
                    var blockHeight = Math.min(product.height_in * sc, shelfHeight - 2);
                    var baseLeft = pos.x_position * sc;

                    for (var f = 0; f < (pos.facings_wide || 1); f++) {
                        var block = document.createElement('div');
                        block.className = 'product-block';
                        if (f > 0) block.classList.add('facing-repeat');

                        block.dataset.art = product.name || '';
                        block.dataset.productId = pos.product_id || '';
                        block.dataset.type = type;

                        var leftPx = bodyLeftPx + baseLeft + f * singleWidth;
                        block.style.width = singleWidth + 'px';
                        block.style.height = blockHeight + 'px';
                        block.style.left = leftPx + 'px';
                        block.style.top = (shelfTopPx + shelfHeight - blockHeight) + 'px';

                        var hasNoBg = !!product.image_no_bg_url;
                        var imgSrc = product.image_no_bg_url || product.image_url;

                        if (imgSrc && blockHeight > 14 && singleWidth > 10) {
                            block.classList.add('product-block-image');
                            if (hasNoBg) block.classList.add('product-no-bg');
                            var imgEl = document.createElement('img');
                            imgEl.src = imgSrc;
                            imgEl.className = 'product-image';
                            imgEl.draggable = false;
                            block.appendChild(imgEl);
                        } else {
                            block.style.backgroundColor = product.color_hex || '#666';
                        }

                        block.style.cursor = 'pointer';
                        block.addEventListener('click', function(e) {
                            e.stopPropagation();
                            selectProductForComparison(product.name || '', pos.product_id || '');
                        });

                        productLayer.appendChild(block);
                    }
                });
            });

            applyComparisonHighlights(type);
        });
    }

    // ── RENDER SINGLE BAY FOR PLANOGRAM ────────────────────────────
    function renderMiniBayPlanogram(container, bay, photoName) {
        container.innerHTML = '';
        container.dataset.bayNumber = bay.bay_number;
        var bayWidthIn = bay.width_in || 49.21;
        var sc = getPlanoScaleForPhoto(photoName, bayWidthIn);

        var productsMap = {};
        (planogramLayout.products || []).forEach(function(p) {
            productsMap[p.id] = p;
        });

        var bays = BayRenderer.normalizeDashboard({ bays: [bay] });
        var layout = BayRenderer.render({
            container: container,
            scale: sc,
            bayGap: 0,
            gluedGap: 0,
            bays: bays,
            onShelf: function(shelfEl, shelf, si, bayObj, bayIdx) {
                shelfEl.dataset.shelfNumber = shelf.shelf_number;
                var hasProducts = shelf.positions && shelf.positions.length > 0;
                if (!hasProducts) {
                    shelfEl.classList.add('empty-shelf');
                    var lbl = document.createElement('span');
                    lbl.className = 'empty-shelf-label';
                    lbl.textContent = 'Empty';
                    shelfEl.appendChild(lbl);
                }
            }
        });

        if (!layout || !layout.length) return;

        var productLayer = document.createElement('div');
        productLayer.className = 'product-layer';
        container.appendChild(productLayer);

        requestAnimationFrame(function() {
            var containerRect = container.getBoundingClientRect();
            var meta = layout[0];
            if (!meta || !meta.bodyEl) return;

            bays[0].shelves.forEach(function(shelf) {
                var sMeta = meta.shelves.find(function(s) { return s.shelf_number === shelf.shelf_number; });
                if (!sMeta || !sMeta.el) return;
                var positions = shelf.positions || [];
                if (!positions.length) return;

                var shelfRect = sMeta.el.getBoundingClientRect();
                var shelfTopPx = shelfRect.top - containerRect.top;
                var shelfHeight = shelfRect.height;
                var bodyRect = meta.bodyEl.getBoundingClientRect();
                var bodyLeftPx = bodyRect.left - containerRect.left;

                positions.forEach(function(pos) {
                    if (pos._phantom) return;
                    var product = productsMap[pos.product_id];
                    if (!product) return;

                    var singleWidth = product.width_in * sc;
                    var blockHeight = Math.min(product.height_in * sc, shelfHeight - 2);
                    var baseLeft = pos.x_position * sc;

                    for (var f = 0; f < (pos.facings_wide || 1); f++) {
                        var block = document.createElement('div');
                        block.className = 'product-block';
                        if (f > 0) block.classList.add('facing-repeat');

                        block.dataset.art = product.name || '';
                        block.dataset.productId = pos.product_id || '';
                        block.dataset.type = 'planogram';

                        var leftPx = bodyLeftPx + baseLeft + f * singleWidth;
                        block.style.width = singleWidth + 'px';
                        block.style.height = blockHeight + 'px';
                        block.style.left = leftPx + 'px';
                        block.style.top = (shelfTopPx + shelfHeight - blockHeight) + 'px';

                        var hasNoBg = !!product.image_no_bg_url;
                        var imgSrc = product.image_no_bg_url || product.image_url;

                        if (imgSrc && blockHeight > 14 && singleWidth > 10) {
                            block.classList.add('product-block-image');
                            if (hasNoBg) block.classList.add('product-no-bg');
                            var imgEl = document.createElement('img');
                            imgEl.src = imgSrc;
                            imgEl.className = 'product-image';
                            imgEl.draggable = false;
                            block.appendChild(imgEl);
                        } else {
                            block.style.backgroundColor = product.color_hex || '#666';
                        }

                        block.style.cursor = 'pointer';
                        block.addEventListener('click', function(e) {
                            e.stopPropagation();
                            selectProductForComparison(product.name || '', pos.product_id || '');
                        });

                        productLayer.appendChild(block);
                    }
                });
            });

            applyComparisonHighlights('planogram');
        });
    }

    // ── COMPARISON LOGIC ───────────────────────────────────────────
    function runComparison() {
        if (!PV.recog.planogramData || !PV.planogramFacings) {
            return;
        }

        var realogramFacings = {};
        var products = PV.recog.planogramData.products || [];
        var bays = PV.recog.planogramData.equipment.bays || [];

        // Count facings in realogram
        bays.forEach(function(bay) {
            (bay.shelves || []).forEach(function(shelf) {
                (shelf.positions || []).forEach(function(pos) {
                    var product = PV.recog.productsMap[pos.product_id];
                    if (!product) return;
                    var art = product.name || '';
                    if (!realogramFacings[art]) {
                        realogramFacings[art] = { count: 0, product: product };
                    }
                    realogramFacings[art].count += (pos.facings_wide || 1);
                });
            });
        });

        // Compare with planogram
        comparisonData = {
            matches: [],
            extra: [],
            missing: [],
            wrongQty: []
        };

        var allArts = new Set([
            ...Object.keys(realogramFacings),
            ...Object.keys(PV.planogramFacings)
        ]);

        allArts.forEach(function(art) {
            var realCount = realogramFacings[art] ? realogramFacings[art].count : 0;
            var planoInfo = PV.planogramFacings[art];
            var planoCount = planoInfo ? planoInfo.facings_wide : 0;
            var product = realogramFacings[art]
                ? realogramFacings[art].product
                : { name: art, image_url: planoInfo ? planoInfo.image_url : '' };

            if (realCount > 0 && planoCount === 0) {
                comparisonData.extra.push({
                    art: art,
                    realCount: realCount,
                    planoCount: planoCount,
                    product: product
                });
            } else if (realCount === 0 && planoCount > 0) {
                comparisonData.missing.push({
                    art: art,
                    realCount: realCount,
                    planoCount: planoCount,
                    product: { name: art, image_url: planoInfo.image_url }
                });
            } else if (realCount !== planoCount) {
                comparisonData.wrongQty.push({
                    art: art,
                    realCount: realCount,
                    planoCount: planoCount,
                    product: product
                });
            } else if (realCount > 0 && realCount === planoCount) {
                comparisonData.matches.push({
                    art: art,
                    realCount: realCount,
                    planoCount: planoCount,
                    product: product
                });
            }
        });

        renderComparisonSummary();
        renderComparisonDetails();
        applyComparisonHighlights('realogram');
        applyComparisonHighlights('planogram');
    }

    function renderComparisonSummary() {
        var container = document.getElementById('compareSummary');
        var total = comparisonData.matches.length + comparisonData.extra.length +
                    comparisonData.missing.length + comparisonData.wrongQty.length;
        var compliance = total > 0
            ? Math.round((comparisonData.matches.length / total) * 100)
            : 0;

        var complianceClass = compliance >= 80 ? 'high' : (compliance >= 50 ? 'medium' : 'low');

        container.innerHTML =
            '<div class="compliance-score">' +
                '<div class="compliance-value ' + complianceClass + '">' + compliance + '%</div>' +
                '<div class="compliance-label">Planogram Compliance</div>' +
            '</div>' +
            '<div class="compare-stats-grid">' +
                '<div class="compare-stat-card highlight-green">' +
                    '<div class="compare-stat-value">' + comparisonData.matches.length + '</div>' +
                    '<div class="compare-stat-label">Matching</div>' +
                '</div>' +
                '<div class="compare-stat-card highlight-red">' +
                    '<div class="compare-stat-value">' + comparisonData.extra.length + '</div>' +
                    '<div class="compare-stat-label">Extra Products</div>' +
                '</div>' +
                '<div class="compare-stat-card highlight-orange">' +
                    '<div class="compare-stat-value">' + comparisonData.missing.length + '</div>' +
                    '<div class="compare-stat-label">Missing</div>' +
                '</div>' +
                '<div class="compare-stat-card highlight-purple">' +
                    '<div class="compare-stat-value">' + comparisonData.wrongQty.length + '</div>' +
                    '<div class="compare-stat-label">Wrong Qty</div>' +
                '</div>' +
            '</div>';
    }

    function renderComparisonDetails() {
        var container = document.getElementById('compareDetails');
        var html = '';

        if (comparisonData.extra.length > 0) {
            html += '<div class="compare-section extra">';
            html += '<div class="compare-section-header">';
            html += '<span>Extra Products (not in planogram)</span>';
            html += '<span class="compare-section-count">' + comparisonData.extra.length + '</span>';
            html += '</div>';
            comparisonData.extra.forEach(function(item) {
                html += renderCompareItem(item, 'extra');
            });
            html += '</div>';
        }

        if (comparisonData.missing.length > 0) {
            html += '<div class="compare-section missing">';
            html += '<div class="compare-section-header">';
            html += '<span>Missing Products (should be on shelf)</span>';
            html += '<span class="compare-section-count">' + comparisonData.missing.length + '</span>';
            html += '</div>';
            comparisonData.missing.forEach(function(item) {
                html += renderCompareItem(item, 'missing');
            });
            html += '</div>';
        }

        if (comparisonData.wrongQty.length > 0) {
            html += '<div class="compare-section wrong-qty">';
            html += '<div class="compare-section-header">';
            html += '<span>Wrong Quantity</span>';
            html += '<span class="compare-section-count">' + comparisonData.wrongQty.length + '</span>';
            html += '</div>';
            comparisonData.wrongQty.forEach(function(item) {
                html += renderCompareItem(item, 'wrong-qty');
            });
            html += '</div>';
        }

        container.innerHTML = html;

        // Add click handlers
        container.querySelectorAll('.compare-product-item').forEach(function(el) {
            el.addEventListener('click', function() {
                var art = el.dataset.art;
                highlightProductInViews(art);
            });
        });
    }

    function renderCompareItem(item, type) {
        var imgUrl = item.product.image_url || item.product.image_no_bg_url || '';
        var thumbHtml = imgUrl
            ? '<img class="compare-product-thumb" src="' + imgUrl + '" alt="">'
            : '<div class="compare-product-thumb" style="background:' + (item.product.color_hex || '#666') + '"></div>';

        var qtyText = '';
        if (type === 'extra') {
            qtyText = '+' + item.realCount;
        } else if (type === 'missing') {
            qtyText = '-' + item.planoCount;
        } else if (type === 'wrong-qty') {
            qtyText = item.realCount + ' / ' + item.planoCount;
        }

        return '<div class="compare-product-item ' + type + '" data-art="' + item.art + '">' +
            thumbHtml +
            '<div class="compare-product-info">' +
                '<div class="compare-product-name">' + item.art + '</div>' +
                '<div class="compare-product-meta">Real: ' + item.realCount + ' | Plan: ' + item.planoCount + '</div>' +
            '</div>' +
            '<div class="compare-product-qty">' + qtyText + '</div>' +
        '</div>';
    }

    // ── HIGHLIGHTING ───────────────────────────────────────────────
    function applyComparisonHighlights(type) {
        if (!comparisonData) return;

        var containers = type === 'realogram'
            ? document.querySelectorAll('[id^="realogram-"] .product-block')
            : document.querySelectorAll('[id^="planogram-"] .product-block');

        var extraArts = new Set(comparisonData.extra.map(function(i) { return i.art; }));
        var missingArts = new Set(comparisonData.missing.map(function(i) { return i.art; }));
        var wrongQtyArts = new Set(comparisonData.wrongQty.map(function(i) { return i.art; }));
        var matchArts = new Set(comparisonData.matches.map(function(i) { return i.art; }));

        containers.forEach(function(block) {
            var art = block.dataset.art;
            block.classList.remove('compare-match', 'compare-extra', 'compare-missing', 'compare-wrong-qty');

            if (extraArts.has(art)) {
                block.classList.add('compare-extra');
            } else if (missingArts.has(art)) {
                block.classList.add('compare-missing');
            } else if (wrongQtyArts.has(art)) {
                block.classList.add('compare-wrong-qty');
            } else if (matchArts.has(art)) {
                block.classList.add('compare-match');
            }
        });
    }

    function highlightProductInViews(art) {
        // Remove existing highlights
        document.querySelectorAll('.product-block.selected-compare').forEach(function(el) {
            el.classList.remove('selected-compare');
        });

        // Highlight matching products
        document.querySelectorAll('.product-block[data-art="' + art + '"]').forEach(function(el) {
            el.classList.add('selected-compare');
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });

        // Also highlight in photo overlay
        if (typeof selectProduct === 'function') {
            selectProduct(art);
        }
    }

    function selectProductForComparison(art, productId) {
        highlightProductInViews(art);

        // Update detail panel
        if (typeof renderDetail === 'function' && PV.recog.productsMap[productId]) {
            renderDetail(PV.recog.productsMap[productId]);
        }
    }

    // ── HELPER FUNCTIONS ───────────────────────────────────────────
    function getPlanoScaleForPhoto(photoName, bayWidthIn) {
        var img = document.getElementById('img-' + photoName);
        if (!img) return 3;
        var photoDisplayW = img.offsetWidth || img.clientWidth;
        if (photoDisplayW < 20) return 3;
        return photoDisplayW / bayWidthIn;
    }

    // Override the original function
    window.renderAllMiniPlanograms = function() {
        renderAllRealograms();
        renderAllPlanograms();
    };

    // Disable planogram facings requirement for product list
    PV.planogramFacings = {};

})();
