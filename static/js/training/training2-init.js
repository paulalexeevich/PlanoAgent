/* Training 2 — Decision Tree: standalone entity with filter rules per node.
 * Each node carries filter_rules {field: value} that determine which products match.
 * The tree is portable — can be saved and applied to any set of photos.
 * Loaded last — requires photo-viewer modules (state, overlay, data, zoom). */

var DT = {
    productMap: {},
    treeData: null,
    activeNode: null,
    savedTreeId: null,
    levelColors: {
        l0: '#e94560',
        l1: '#f9c74f',
        l2: '#90be6d',
        pkg: '#00b4d8',
        brand: '#7209b7',
    },
    FILTER_FIELDS: ['category_l0', 'category_l1', 'category_l2', 'package_type', 'brand'],
    FIELD_LABELS: {
        category_l0: 'L0',
        category_l1: 'L1',
        category_l2: 'L2',
        package_type: 'Pkg',
        brand: 'Brand',
    },
};

// ═══════════════════════════════════════════════════════════════════════
// FILTER RULES ENGINE — portable matching that works on any product map
// ═══════════════════════════════════════════════════════════════════════

function productMatchesRules(product, filterRules) {
    var keys = Object.keys(filterRules);
    if (keys.length === 0) return true;
    for (var i = 0; i < keys.length; i++) {
        var field = keys[i];
        var expected = filterRules[field];
        var actual = product[field] || '';
        if (actual !== expected) return false;
    }
    return true;
}

function findMatchingProductIds(productMap, filterRules) {
    var ids = new Set();
    Object.keys(productMap).forEach(function(pid) {
        if (productMatchesRules(productMap[pid], filterRules)) {
            ids.add(pid);
        }
    });
    return ids;
}

function countMatchingProducts(productMap, filterRules) {
    var count = 0;
    Object.keys(productMap).forEach(function(pid) {
        if (productMatchesRules(productMap[pid], filterRules)) count++;
    });
    return count;
}

// ═══════════════════════════════════════════════════════════════════════
// TREE BUILDER — generates tree with filter_rules from product map data
// ═══════════════════════════════════════════════════════════════════════

function buildDecisionTree(productMap) {
    var idCounter = 0;
    function nextId() { return 'node_' + (++idCounter); }

    var root = {
        id: 'root',
        name: 'All Products',
        level: 'root',
        filter_rules: {},
        children: [],
    };

    var l0Groups = {};
    Object.keys(productMap).forEach(function(pid) {
        var p = productMap[pid];
        var l0 = p.category_l0 || '(unknown)';
        if (!l0Groups[l0]) l0Groups[l0] = [];
        l0Groups[l0].push(p);
    });

    Object.keys(l0Groups).sort().forEach(function(l0Name) {
        var l0Products = l0Groups[l0Name];
        var l0Rules = l0Name === '(unknown)' ? {} : { category_l0: l0Name };
        var l0Node = {
            id: nextId(),
            name: l0Name,
            level: 'l0',
            filter_rules: l0Rules,
            children: [],
        };

        var l1Groups = {};
        l0Products.forEach(function(p) {
            var l1 = p.category_l1 || '(unknown)';
            if (!l1Groups[l1]) l1Groups[l1] = [];
            l1Groups[l1].push(p);
        });

        Object.keys(l1Groups).sort().forEach(function(l1Name) {
            var l1Products = l1Groups[l1Name];
            var l1Rules = Object.assign({}, l0Rules);
            if (l1Name !== '(unknown)') l1Rules.category_l1 = l1Name;
            var l1Node = {
                id: nextId(),
                name: l1Name,
                level: 'l1',
                filter_rules: l1Rules,
                children: [],
            };

            var l2Groups = {};
            l1Products.forEach(function(p) {
                var l2 = p.category_l2 || '';
                if (!l2Groups[l2]) l2Groups[l2] = [];
                l2Groups[l2].push(p);
            });

            Object.keys(l2Groups).sort().forEach(function(l2Name) {
                if (!l2Name) return;
                var l2Products = l2Groups[l2Name];
                var l2Rules = Object.assign({}, l1Rules, { category_l2: l2Name });
                var l2Node = {
                    id: nextId(),
                    name: l2Name,
                    level: 'l2',
                    filter_rules: l2Rules,
                    children: [],
                };

                var pkgGroups = {};
                l2Products.forEach(function(p) {
                    var pkg = p.package_type || '';
                    if (!pkgGroups[pkg]) pkgGroups[pkg] = [];
                    pkgGroups[pkg].push(p);
                });

                Object.keys(pkgGroups).sort().forEach(function(pkgName) {
                    if (!pkgName) return;
                    var pkgProducts = pkgGroups[pkgName];
                    var pkgRules = Object.assign({}, l2Rules, { package_type: pkgName });
                    var pkgNode = {
                        id: nextId(),
                        name: pkgName,
                        level: 'pkg',
                        filter_rules: pkgRules,
                        children: [],
                    };

                    var brandGroups = {};
                    pkgProducts.forEach(function(p) {
                        var brand = p.brand || '';
                        if (!brandGroups[brand]) brandGroups[brand] = [];
                        brandGroups[brand].push(p);
                    });

                    Object.keys(brandGroups).sort().forEach(function(brandName) {
                        if (!brandName) return;
                        var brandRules = Object.assign({}, pkgRules, { brand: brandName });
                        pkgNode.children.push({
                            id: nextId(),
                            name: brandName,
                            level: 'brand',
                            filter_rules: brandRules,
                            children: [],
                        });
                    });

                    l2Node.children.push(pkgNode);
                });

                l1Node.children.push(l2Node);
            });

            if (l2Groups['']) {
                var pkgGroups2 = {};
                l2Groups[''].forEach(function(p) {
                    var pkg = p.package_type || '(no package)';
                    if (!pkgGroups2[pkg]) pkgGroups2[pkg] = [];
                    pkgGroups2[pkg].push(p);
                });
                Object.keys(pkgGroups2).sort().forEach(function(pkgName) {
                    var pkgRules = Object.assign({}, l1Rules);
                    if (pkgName !== '(no package)') pkgRules.package_type = pkgName;
                    l1Node.children.push({
                        id: nextId(),
                        name: pkgName,
                        level: 'pkg',
                        filter_rules: pkgRules,
                        children: [],
                    });
                });
            }

            l0Node.children.push(l1Node);
        });

        root.children.push(l0Node);
    });

    return root;
}

// ═══════════════════════════════════════════════════════════════════════
// TREE SERIALIZATION — convert to/from JSON-safe format
// ═══════════════════════════════════════════════════════════════════════

function serializeTree(node) {
    return {
        id: node.id,
        name: node.name,
        level: node.level,
        filter_rules: node.filter_rules,
        children: (node.children || []).map(serializeTree),
    };
}

function deserializeTree(data) {
    return {
        id: data.id || 'root',
        name: data.name || '',
        level: data.level || 'root',
        filter_rules: data.filter_rules || {},
        children: (data.children || []).map(deserializeTree),
    };
}

// ═══════════════════════════════════════════════════════════════════════
// RENDER TREE — nested collapsible buttons with filter rules tooltip
// ═══════════════════════════════════════════════════════════════════════

function renderTree(container, node, depth) {
    if (!node.children || node.children.length === 0) return;

    node.children.forEach(function(child) {
        var hasChildren = child.children && child.children.length > 0;
        var count = countMatchingProducts(DT.productMap, child.filter_rules);

        var level = document.createElement('div');
        level.className = 'dt-level';

        var btn = document.createElement('button');
        btn.className = 'dt-node-btn' + (hasChildren ? ' has-children' : '');
        btn.setAttribute('data-node-id', child.id);
        btn.setAttribute('data-level', child.level);

        var rulesTitle = formatFilterRules(child.filter_rules);
        btn.setAttribute('title', rulesTitle || 'All products');

        var caret = hasChildren
            ? '<span class="dt-caret expanded">&#9654;</span>'
            : '<span style="width:14px;display:inline-block"></span>';

        btn.innerHTML =
            caret +
            '<span class="dt-level-dot ' + child.level + '"></span>' +
            '<span class="dt-node-name">' + escHtml(child.name) + '</span>' +
            '<span class="dt-node-count">' + count + '</span>';

        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            if (hasChildren && e.target.closest('.dt-caret')) {
                toggleChildren(level);
                return;
            }
            selectTreeNode(child);
        });

        level.appendChild(btn);

        if (hasChildren) {
            var childContainer = document.createElement('div');
            childContainer.className = 'dt-children';
            renderTree(childContainer, child, depth + 1);
            level.appendChild(childContainer);
        }

        container.appendChild(level);
    });
}

function formatFilterRules(rules) {
    var keys = Object.keys(rules);
    if (keys.length === 0) return 'No filter (all products)';
    return keys.map(function(k) {
        var label = DT.FIELD_LABELS[k] || k;
        return label + ' = "' + rules[k] + '"';
    }).join('\n');
}

function toggleChildren(levelEl) {
    var childContainer = levelEl.querySelector('.dt-children');
    var caret = levelEl.querySelector('.dt-caret');
    if (!childContainer) return;

    if (childContainer.classList.contains('collapsed')) {
        childContainer.classList.remove('collapsed');
        childContainer.style.maxHeight = childContainer.scrollHeight + 'px';
        if (caret) caret.classList.add('expanded');
    } else {
        childContainer.style.maxHeight = childContainer.scrollHeight + 'px';
        requestAnimationFrame(function() {
            childContainer.classList.add('collapsed');
            childContainer.style.maxHeight = '0px';
        });
        if (caret) caret.classList.remove('expanded');
    }
}

function escHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ═══════════════════════════════════════════════════════════════════════
// NODE SELECTION & BOUNDING BOX HIGHLIGHTING
// ═══════════════════════════════════════════════════════════════════════

function selectTreeNode(node) {
    if (DT.activeNode && DT.activeNode.id === node.id) {
        clearTreeFilter();
        return;
    }

    DT.activeNode = node;

    document.querySelectorAll('.dt-node-btn.active').forEach(function(el) {
        el.classList.remove('active');
    });
    var targetBtn = document.querySelector('.dt-node-btn[data-node-id="' + node.id + '"]');
    if (targetBtn) targetBtn.classList.add('active');

    document.getElementById('activeFilterBadge').style.display = '';
    document.getElementById('activeFilterName').textContent = node.name;

    var rulesEl = document.getElementById('activeFilterRules');
    if (rulesEl) {
        var ruleKeys = Object.keys(node.filter_rules);
        if (ruleKeys.length > 0) {
            rulesEl.textContent = ruleKeys.map(function(k) {
                return (DT.FIELD_LABELS[k] || k) + '=' + node.filter_rules[k];
            }).join(', ');
            rulesEl.style.display = '';
        } else {
            rulesEl.style.display = 'none';
        }
    }

    applyTreeHighlight(node);
    updateAreaStats(node);
}

function clearTreeFilter() {
    DT.activeNode = null;

    document.querySelectorAll('.dt-node-btn.active').forEach(function(el) {
        el.classList.remove('active');
    });
    document.getElementById('activeFilterBadge').style.display = 'none';

    removeTreeHighlight();
    hideAreaStats();
}

function applyTreeHighlight(node) {
    if (!node) { removeTreeHighlight(); return; }

    var matchSet = findMatchingProductIds(DT.productMap, node.filter_rules);
    var color = DT.levelColors[node.level] || '#4a9eff';

    PV.photos.forEach(function(name) {
        var data = PV.photoData[name];
        if (!data) return;

        document.querySelectorAll('#svg-' + CSS.escape(name) + ' .bbox-product').forEach(function(el) {
            var idx = parseInt(el.getAttribute('data-product-idx'));
            var p = data.products[idx];
            if (!p) return;
            var isMatch = matchSet.has(p.art) || matchSet.has(p.product_id);

            el.classList.remove('dt-match', 'dt-dimmed');
            if (isMatch) {
                el.classList.add('dt-match');
                el.setAttribute('stroke', color);
                el.setAttribute('fill', color + '30');
                el.setAttribute('stroke-width', '8');
            } else {
                el.classList.add('dt-dimmed');
            }
        });

        document.querySelectorAll('#svg-' + CSS.escape(name) + ' .bbox-label-bg').forEach(function(el) {
            var art = el.getAttribute('data-art');
            var isMatch = false;
            data.products.forEach(function(p) {
                if ((p.art === art || p.product_id === art) && (matchSet.has(p.art) || matchSet.has(p.product_id))) {
                    isMatch = true;
                }
            });
            el.style.opacity = isMatch ? '1' : '0.15';
        });

        document.querySelectorAll('#svg-' + CSS.escape(name) + ' .bbox-label').forEach(function(el) {
            var art = el.getAttribute('data-art');
            var isMatch = false;
            data.products.forEach(function(p) {
                if ((p.art === art || p.product_id === art) && (matchSet.has(p.art) || matchSet.has(p.product_id))) {
                    isMatch = true;
                }
            });
            el.style.opacity = isMatch ? '1' : '0.1';
        });
    });
}

function removeTreeHighlight() {
    document.querySelectorAll('.bbox-product').forEach(function(el) {
        el.classList.remove('dt-match', 'dt-dimmed');
    });
    renderAllOverlays();
}

// ═══════════════════════════════════════════════════════════════════════
// AREA STATS — how much shelf space this node occupies
// ═══════════════════════════════════════════════════════════════════════

function updateAreaStats(node) {
    var statsEl = document.getElementById('dtStats');
    var matchSet = findMatchingProductIds(DT.productMap, node.filter_rules);
    var totalProducts = 0;
    var matchProducts = 0;
    var totalArea = 0;
    var matchArea = 0;

    PV.photos.forEach(function(name) {
        var data = PV.photoData[name];
        if (!data) return;

        data.products.forEach(function(p) {
            if (p.is_duplicated) return;
            var w = Math.abs(p.x2 - p.x1);
            var h = Math.abs(p.y2 - p.y1);
            var area = w * h;
            totalProducts++;
            totalArea += area;

            if (matchSet.has(p.art) || matchSet.has(p.product_id)) {
                matchProducts++;
                matchArea += area;
            }
        });
    });

    var areaPct = totalArea > 0 ? (matchArea / totalArea * 100) : 0;
    var facingPct = totalProducts > 0 ? (matchProducts / totalProducts * 100) : 0;
    var color = DT.levelColors[node.level] || '#4a9eff';

    statsEl.innerHTML =
        '<div class="dt-stats-grid">' +
        '<div class="dt-stat-item"><div class="dt-stat-label">Matched Facings</div>' +
        '<div class="dt-stat-value">' + matchProducts + ' <span style="font-size:11px;color:var(--text-secondary)">/ ' + totalProducts + '</span></div></div>' +
        '<div class="dt-stat-item"><div class="dt-stat-label">Facing Share</div>' +
        '<div class="dt-stat-value" style="color:' + color + '">' + facingPct.toFixed(1) + '%</div></div>' +
        '<div class="dt-stat-item"><div class="dt-stat-label">Unique SKUs</div>' +
        '<div class="dt-stat-value">' + matchSet.size + '</div></div>' +
        '<div class="dt-stat-item"><div class="dt-stat-label">Area Share</div>' +
        '<div class="dt-stat-value" style="color:' + color + '">' + areaPct.toFixed(1) + '%</div></div>' +
        '</div>';

    statsEl.style.display = '';
    renderAreaBreakdown(node);
}

function renderAreaBreakdown(node) {
    if (!node.children || node.children.length === 0) return;

    var container = document.getElementById('dtStats');
    var parentMatchSet = findMatchingProductIds(DT.productMap, node.filter_rules);
    var totalArea = 0;
    var childAreas = {};

    PV.photos.forEach(function(name) {
        var data = PV.photoData[name];
        if (!data) return;

        data.products.forEach(function(p) {
            if (p.is_duplicated) return;
            if (!parentMatchSet.has(p.art) && !parentMatchSet.has(p.product_id)) return;

            var w = Math.abs(p.x2 - p.x1);
            var h = Math.abs(p.y2 - p.y1);
            var area = w * h;
            totalArea += area;

            node.children.forEach(function(child) {
                var childSet = findMatchingProductIds(DT.productMap, child.filter_rules);
                if (childSet.has(p.art) || childSet.has(p.product_id)) {
                    childAreas[child.id] = (childAreas[child.id] || 0) + area;
                }
            });
        });
    });

    if (totalArea === 0) return;

    var html = '<div class="dt-area-bar"><h4>Children Area Share</h4>';
    node.children.forEach(function(child) {
        var pct = totalArea > 0 ? ((childAreas[child.id] || 0) / totalArea * 100) : 0;
        var color = DT.levelColors[child.level] || '#4a9eff';
        html +=
            '<div class="dt-area-row">' +
            '<span class="dt-level-dot ' + child.level + '"></span>' +
            '<span class="dt-area-name">' + escHtml(child.name) + '</span>' +
            '<span class="dt-area-pct">' + pct.toFixed(1) + '%</span>' +
            '<span class="dt-area-bar-track"><span class="dt-area-bar-fill" style="width:' + pct + '%;background:' + color + '"></span></span>' +
            '</div>';
    });
    html += '</div>';
    container.innerHTML += html;
}

function hideAreaStats() {
    document.getElementById('dtStats').style.display = 'none';
}

// ═══════════════════════════════════════════════════════════════════════
// SAVE / LOAD — persist decision tree to Supabase
// ═══════════════════════════════════════════════════════════════════════

function saveDecisionTree() {
    if (!DT.treeData) return;

    var nameInput = document.getElementById('dtSaveName');
    var name = (nameInput && nameInput.value.trim()) || 'Coffee Decision Tree';

    var payload = {
        name: name,
        description: 'Auto-generated from product map',
        tree_data: serializeTree(DT.treeData),
    };

    var saveBtn = document.getElementById('btnSaveTree');
    if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'Saving...'; }

    fetch('/api/coffee-decision-tree/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.status === 'success') {
            DT.savedTreeId = data.saved.id;
            showTreeMessage('Saved! ID: ' + data.saved.id, 'success');
            loadTreeList();
        } else {
            showTreeMessage('Save failed: ' + (data.error || 'unknown'), 'error');
        }
    })
    .catch(function(err) {
        showTreeMessage('Save error: ' + err.message, 'error');
    })
    .finally(function() {
        if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Save Tree'; }
    });
}

function loadDecisionTreeById(treeId) {
    var loadingEl = document.getElementById('dtLoading');
    loadingEl.style.display = '';
    loadingEl.innerHTML = '<div class="btn-spinner"></div><span>Loading saved tree...</span>';
    document.getElementById('dtTreeContainer').style.display = 'none';

    fetch('/api/coffee-decision-tree/load/' + treeId)
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.status !== 'success') {
            loadingEl.innerHTML = '<span style="color:var(--accent-red)">Load failed: ' + (data.error || 'unknown') + '</span>';
            return;
        }

        DT.treeData = deserializeTree(data.tree.tree_data);
        DT.savedTreeId = data.tree.id;
        renderFullTree();
        showTreeMessage('Loaded: ' + data.tree.name, 'success');
    })
    .catch(function(err) {
        loadingEl.innerHTML = '<span style="color:var(--accent-red)">Error: ' + err.message + '</span>';
    });
}

function loadTreeList() {
    fetch('/api/coffee-decision-tree/list')
    .then(function(r) { return r.json(); })
    .then(function(data) {
        var listEl = document.getElementById('dtSavedList');
        if (!listEl || data.status !== 'success') return;

        if (data.trees.length === 0) {
            listEl.innerHTML = '<div class="dt-no-saved">No saved trees</div>';
            return;
        }

        var html = '';
        data.trees.forEach(function(t) {
            var dateStr = new Date(t.updated_at).toLocaleDateString();
            html +=
                '<div class="dt-saved-item" data-tree-id="' + t.id + '">' +
                '<span class="dt-saved-name">' + escHtml(t.name) + '</span>' +
                '<span class="dt-saved-date">' + dateStr + '</span>' +
                '</div>';
        });
        listEl.innerHTML = html;

        listEl.querySelectorAll('.dt-saved-item').forEach(function(item) {
            item.addEventListener('click', function() {
                loadDecisionTreeById(parseInt(item.getAttribute('data-tree-id')));
            });
        });
    });
}

function showTreeMessage(msg, type) {
    var el = document.getElementById('dtMessage');
    if (!el) return;
    el.textContent = msg;
    el.className = 'dt-message dt-message-' + type;
    el.style.display = '';
    setTimeout(function() { el.style.display = 'none'; }, 3000);
}

// ═══════════════════════════════════════════════════════════════════════
// RENDER FULL TREE UI
// ═══════════════════════════════════════════════════════════════════════

function renderFullTree() {
    document.getElementById('dtLoading').style.display = 'none';
    var container = document.getElementById('dtTreeContainer');
    container.style.display = '';
    container.innerHTML = '';

    var legend = document.createElement('div');
    legend.className = 'dt-level-legend';
    legend.innerHTML =
        '<span class="dt-legend-item"><span class="dt-level-dot l0"></span> L0</span>' +
        '<span class="dt-legend-item"><span class="dt-level-dot l1"></span> L1</span>' +
        '<span class="dt-legend-item"><span class="dt-level-dot l2"></span> L2</span>' +
        '<span class="dt-legend-item"><span class="dt-level-dot pkg"></span> Package</span>' +
        '<span class="dt-legend-item"><span class="dt-level-dot brand"></span> Brand</span>';
    container.appendChild(legend);

    renderTree(container, DT.treeData, 0);

    var total = countMatchingProducts(DT.productMap, {});
    var mapped = Object.keys(DT.productMap).length;
    console.log('[DT] Tree rendered:', mapped, 'products in map,',
        DT.treeData.children.length, 'top-level nodes');
}

// ═══════════════════════════════════════════════════════════════════════
// INITIALIZE — load product map, build tree, setup events
// ═══════════════════════════════════════════════════════════════════════

function initDecisionTree() {
    fetch('/api/product-map')
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.status !== 'success') {
            document.getElementById('dtLoading').innerHTML =
                '<span style="color:var(--accent-red)">Failed to load product map: ' + (data.error || 'unknown') + '</span>';
            return;
        }

        DT.productMap = data.product_map;
        DT.treeData = buildDecisionTree(DT.productMap);
        renderFullTree();
        loadTreeList();
    })
    .catch(function(err) {
        document.getElementById('dtLoading').innerHTML =
            '<span style="color:var(--accent-red)">Error: ' + err.message + '</span>';
    });
}

// Re-apply highlight after overlay re-render
var _origRenderAllOverlays = window.renderAllOverlays;
window.renderAllOverlays = function() {
    _origRenderAllOverlays();
    if (DT.activeNode) {
        setTimeout(function() { applyTreeHighlight(DT.activeNode); }, 10);
    }
};

// ═══════════════════════════════════════════════════════════════════════
// PANEL & TAB SWITCHING
// ═══════════════════════════════════════════════════════════════════════

function openPanelTab(tab) {
    document.getElementById('sidePanel').classList.add('open');
    switchTab(tab);
    setTimeout(zoomFitAll, 280);
}

function closeSidePanel() {
    document.getElementById('sidePanel').classList.remove('open');
    setTimeout(zoomFitAll, 280);
}

function switchTab(tab) {
    document.querySelectorAll('.side-panel-tab').forEach(function(b) {
        b.classList.toggle('active', b.getAttribute('data-tab') === tab);
    });
    document.getElementById('tabTree').style.display = tab === 'tree' ? '' : 'none';
    document.getElementById('tabAnalytics').style.display = tab === 'analytics' ? '' : 'none';
}

// ═══════════════════════════════════════════════════════════════════════
// GRID BUILDER (photos only, no planogram section)
// ═══════════════════════════════════════════════════════════════════════

function buildTrainingGrid(photoNames) {
    var grid = document.getElementById('photosGrid');
    grid.innerHTML = '';
    var loadedCount = 0;

    photoNames.forEach(function(name) {
        var card = document.createElement('div');
        card.className = 'photo-card';
        card.id = 'card-' + name;
        card.innerHTML =
            '<div class="photo-header"><span class="photo-title">' + name + '</span></div>' +
            '<div class="canvas-inner" id="canvas-' + name + '">' +
            '<img id="img-' + name + '" alt="' + name + '">' +
            '<svg id="svg-' + name + '" xmlns="http://www.w3.org/2000/svg"></svg>' +
            '</div>';
        grid.appendChild(card);

        var img = document.getElementById('img-' + name);
        img.onload = function() {
            PV.naturalSizes[name] = { w: img.naturalWidth, h: img.naturalHeight };
            fetchPhotoData(name);
            loadedCount++;
            if (loadedCount === photoNames.length) setTimeout(zoomFitAll, 50);
        };
        img.src = '/demo-images/' + name + '.jpg';
    });
}

(function() {
    var origBuildGrid = window.buildGrid;
    window.buildGrid = function(photoNames) {
        if (typeof TRAINING2_MODE !== 'undefined' && TRAINING2_MODE) {
            buildTrainingGrid(photoNames);
        } else {
            origBuildGrid(photoNames);
        }
    };
})();

// ═══════════════════════════════════════════════════════════════════════
// TOOLBAR & SETTINGS — event wiring
// ═══════════════════════════════════════════════════════════════════════

document.querySelector('.settings-btn').addEventListener('click', function(e) {
    e.stopPropagation();
    document.getElementById('settingsMenu').classList.toggle('open');
});

document.getElementById('viewModeToggle').addEventListener('click', function(e) {
    var btn = e.target.closest('[data-view]');
    if (btn) setView(btn.dataset.view, btn);
});

document.getElementById('photoSelect').addEventListener('change', function(e) {
    loadSinglePhoto(e.target.value);
});

document.querySelector('[data-action="zoom-out"]').addEventListener('click', function() { zoomAll(-0.05); });
document.querySelector('[data-action="zoom-in"]').addEventListener('click', function() { zoomAll(0.05); });
document.querySelector('[data-action="zoom-fit"]').addEventListener('click', function() { zoomFitAll(); });

document.getElementById('showProducts').addEventListener('change', renderAllOverlays);
document.getElementById('showShelves').addEventListener('change', renderAllOverlays);
document.getElementById('showLabels').addEventListener('change', renderAllOverlays);

document.querySelectorAll('.side-panel-tab').forEach(function(btn) {
    btn.addEventListener('click', function() { switchTab(btn.dataset.tab); });
});

document.querySelector('.side-panel-close').addEventListener('click', closeSidePanel);
document.getElementById('clearFilterBtn').addEventListener('click', clearTreeFilter);

if (document.getElementById('searchInput')) {
    document.getElementById('searchInput').addEventListener('input', filterProductList);
}

document.getElementById('btnSaveTree').addEventListener('click', saveDecisionTree);

document.getElementById('btnGenerateTree').addEventListener('click', function() {
    if (!DT.productMap || Object.keys(DT.productMap).length === 0) return;
    DT.treeData = buildDecisionTree(DT.productMap);
    DT.savedTreeId = null;
    clearTreeFilter();
    renderFullTree();
    showTreeMessage('Tree regenerated from product map', 'success');
});

// Grid events
var grid = document.getElementById('photosGrid');

grid.addEventListener('wheel', function(e) {
    e.preventDefault();
    zoomAll(e.deltaY > 0 ? -0.02 : 0.02);
}, { passive: false });

grid.addEventListener('mousedown', function(e) {
    if (e.target.closest('.bbox-product') || e.target.closest('.bbox-shelf')) return;
    PV.drag.active = true;
    PV.drag.startX = e.clientX;
    PV.drag.startY = e.clientY;
    PV.drag.scrollX = grid.scrollLeft;
    PV.drag.scrollY = grid.scrollTop;
    grid.classList.add('dragging');
    e.preventDefault();
});

window.addEventListener('mousemove', function(e) {
    if (!PV.drag.active) return;
    grid.scrollLeft = PV.drag.scrollX - (e.clientX - PV.drag.startX);
    grid.scrollTop = PV.drag.scrollY - (e.clientY - PV.drag.startY);
});

window.addEventListener('mouseup', function() {
    if (PV.drag.active) { PV.drag.active = false; grid.classList.remove('dragging'); }
});

grid.addEventListener('mousedown', function() { PV.drag.distance = 0; });
grid.addEventListener('mousemove', function() { if (PV.drag.active) PV.drag.distance++; });
grid.addEventListener('click', function(e) {
    if (PV.drag.distance > 3) return;
    if (e.target.tagName === 'IMG' || e.target.classList.contains('photos-grid') ||
        e.target.classList.contains('photo-card')) {
        clearSelection();
    }
});

document.addEventListener('click', function(e) {
    var menu = document.getElementById('settingsMenu');
    if (menu.classList.contains('open') && !e.target.closest('.settings-dropdown')) {
        menu.classList.remove('open');
    }
});

// ═══════════════════════════════════════════════════════════════════════
// INITIAL LOAD
// ═══════════════════════════════════════════════════════════════════════

PV.planogramFacings = {};
PV.salesData = {};

if (PV.photos.length > 0) loadAllPhotos();
setTimeout(initDecisionTree, 300);
