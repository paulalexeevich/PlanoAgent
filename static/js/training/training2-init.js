/* Training 2 — Decision Tree: interactive category tree with photo bounding-box highlighting.
 * Loaded last — requires photo-viewer modules (state, overlay, data, zoom). */

var DT = {
    productMap: {},
    treeData: null,
    activeFilter: null,
    matchingProductIds: new Set(),
    levelColors: {
        l0: '#e94560',
        l1: '#f9c74f',
        l2: '#90be6d',
        pkg: '#00b4d8',
        brand: '#7209b7',
    },
};

// ── Build tree from flat product map ──────────────────────────────────

function buildDecisionTree(productMap) {
    var root = { name: 'All Products', level: 'root', children: {}, productIds: new Set() };

    Object.keys(productMap).forEach(function(pid) {
        var p = productMap[pid];
        root.productIds.add(pid);

        var l0 = p.category_l0 || '(unknown)';
        var l1 = p.category_l1 || '(unknown)';
        var l2 = p.category_l2 || '';
        var pkg = p.package_type || '';
        var brand = p.brand || '';

        if (!root.children[l0]) {
            root.children[l0] = { name: l0, level: 'l0', children: {}, productIds: new Set() };
        }
        root.children[l0].productIds.add(pid);

        var l0Node = root.children[l0];
        if (!l0Node.children[l1]) {
            l0Node.children[l1] = { name: l1, level: 'l1', children: {}, productIds: new Set() };
        }
        l0Node.children[l1].productIds.add(pid);

        var l1Node = l0Node.children[l1];
        if (l2) {
            if (!l1Node.children[l2]) {
                l1Node.children[l2] = { name: l2, level: 'l2', children: {}, productIds: new Set() };
            }
            l1Node.children[l2].productIds.add(pid);

            var l2Node = l1Node.children[l2];
            if (pkg) {
                if (!l2Node.children[pkg]) {
                    l2Node.children[pkg] = { name: pkg, level: 'pkg', children: {}, productIds: new Set() };
                }
                l2Node.children[pkg].productIds.add(pid);

                var pkgNode = l2Node.children[pkg];
                if (brand) {
                    if (!pkgNode.children[brand]) {
                        pkgNode.children[brand] = { name: brand, level: 'brand', children: {}, productIds: new Set() };
                    }
                    pkgNode.children[brand].productIds.add(pid);
                }
            } else if (brand) {
                if (!l2Node.children[brand]) {
                    l2Node.children[brand] = { name: brand, level: 'brand', children: {}, productIds: new Set() };
                }
                l2Node.children[brand].productIds.add(pid);
            }
        } else if (pkg) {
            if (!l1Node.children[pkg]) {
                l1Node.children[pkg] = { name: pkg, level: 'pkg', children: {}, productIds: new Set() };
            }
            l1Node.children[pkg].productIds.add(pid);
        }
    });

    return root;
}

// ── Render tree as nested buttons ─────────────────────────────────────

function renderTree(container, node, depth) {
    var childKeys = Object.keys(node.children).sort();
    if (childKeys.length === 0) return;

    childKeys.forEach(function(key) {
        var child = node.children[key];
        var hasChildren = Object.keys(child.children).length > 0;
        var count = child.productIds.size;

        var level = document.createElement('div');
        level.className = 'dt-level';

        var btn = document.createElement('button');
        btn.className = 'dt-node-btn' + (hasChildren ? ' has-children' : '');
        btn.setAttribute('data-node-path', getNodePath(child, node, key));
        btn.setAttribute('data-level', child.level);

        var caret = '';
        if (hasChildren) {
            caret = '<span class="dt-caret expanded">&#9654;</span>';
        } else {
            caret = '<span style="width:14px;display:inline-block"></span>';
        }

        btn.innerHTML =
            caret +
            '<span class="dt-level-dot ' + child.level + '"></span>' +
            '<span class="dt-node-name" title="' + escHtml(child.name) + '">' + escHtml(child.name) + '</span>' +
            '<span class="dt-node-count">' + count + '</span>';

        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            if (hasChildren && e.target.closest('.dt-caret')) {
                toggleChildren(level);
                return;
            }
            selectTreeNode(child, key);
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

function getNodePath(child, parent, key) {
    return child.level + ':' + key;
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

// ── Node selection & highlighting ─────────────────────────────────────

function selectTreeNode(node, key) {
    var filterKey = node.level + ':' + node.name;

    if (DT.activeFilter === filterKey) {
        clearTreeFilter();
        return;
    }

    DT.activeFilter = filterKey;
    DT.matchingProductIds = node.productIds;

    document.querySelectorAll('.dt-node-btn.active').forEach(function(el) {
        el.classList.remove('active');
    });
    var allBtns = document.querySelectorAll('.dt-node-btn');
    allBtns.forEach(function(btn) {
        if (btn.getAttribute('data-node-path') === node.level + ':' + key) {
            btn.classList.add('active');
        }
    });

    document.getElementById('activeFilterBadge').style.display = '';
    document.getElementById('activeFilterName').textContent = node.name;

    applyTreeHighlight();
    updateAreaStats(node);
}

function clearTreeFilter() {
    DT.activeFilter = null;
    DT.matchingProductIds = new Set();

    document.querySelectorAll('.dt-node-btn.active').forEach(function(el) {
        el.classList.remove('active');
    });
    document.getElementById('activeFilterBadge').style.display = 'none';

    removeTreeHighlight();
    hideAreaStats();
}

function applyTreeHighlight() {
    var matchSet = DT.matchingProductIds;
    if (!matchSet || matchSet.size === 0) {
        removeTreeHighlight();
        return;
    }

    PV.photos.forEach(function(name) {
        var data = PV.photoData[name];
        if (!data) return;

        document.querySelectorAll('#svg-' + CSS.escape(name) + ' .bbox-product').forEach(function(el) {
            var productId = el.getAttribute('data-art');
            var externalPid = '';
            var idx = parseInt(el.getAttribute('data-product-idx'));
            if (data.products[idx]) {
                externalPid = data.products[idx].product_id || '';
            }

            var isMatch = matchSet.has(productId) || matchSet.has(externalPid);

            el.classList.remove('dt-match', 'dt-dimmed');
            if (isMatch) {
                el.classList.add('dt-match');
                var color = DT.levelColors[getActiveLevel()] || '#4a9eff';
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

function getActiveLevel() {
    if (!DT.activeFilter) return '';
    return DT.activeFilter.split(':')[0];
}

// ── Area stats (how much shelf space does this node occupy) ───────────

function updateAreaStats(node) {
    var statsEl = document.getElementById('dtStats');
    var matchSet = node.productIds;
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
        '<div class="dt-stat-item">' +
        '<div class="dt-stat-label">Matched Facings</div>' +
        '<div class="dt-stat-value">' + matchProducts + ' <span style="font-size:11px;color:var(--text-secondary)">/ ' + totalProducts + '</span></div>' +
        '</div>' +
        '<div class="dt-stat-item">' +
        '<div class="dt-stat-label">Facing Share</div>' +
        '<div class="dt-stat-value" style="color:' + color + '">' + facingPct.toFixed(1) + '%</div>' +
        '</div>' +
        '<div class="dt-stat-item">' +
        '<div class="dt-stat-label">Unique SKUs</div>' +
        '<div class="dt-stat-value">' + matchSet.size + '</div>' +
        '</div>' +
        '<div class="dt-stat-item">' +
        '<div class="dt-stat-label">Area Share</div>' +
        '<div class="dt-stat-value" style="color:' + color + '">' + areaPct.toFixed(1) + '%</div>' +
        '</div>' +
        '</div>';

    statsEl.style.display = '';

    renderAreaBreakdown(node);
}

function renderAreaBreakdown(node) {
    var childKeys = Object.keys(node.children).sort();
    if (childKeys.length === 0) return;

    var container = document.getElementById('dtStats');
    var totalArea = 0;
    var childAreas = {};

    PV.photos.forEach(function(name) {
        var data = PV.photoData[name];
        if (!data) return;

        data.products.forEach(function(p) {
            if (p.is_duplicated) return;
            if (!node.productIds.has(p.art) && !node.productIds.has(p.product_id)) return;

            var w = Math.abs(p.x2 - p.x1);
            var h = Math.abs(p.y2 - p.y1);
            var area = w * h;
            totalArea += area;

            childKeys.forEach(function(key) {
                var child = node.children[key];
                if (child.productIds.has(p.art) || child.productIds.has(p.product_id)) {
                    childAreas[key] = (childAreas[key] || 0) + area;
                }
            });
        });
    });

    if (totalArea === 0) return;

    var childLevel = node.children[childKeys[0]] ? node.children[childKeys[0]].level : 'l0';
    var color = DT.levelColors[childLevel] || '#4a9eff';

    var html = '<div class="dt-area-bar"><h4>Children Area Share</h4>';
    childKeys.forEach(function(key) {
        var pct = totalArea > 0 ? ((childAreas[key] || 0) / totalArea * 100) : 0;
        html +=
            '<div class="dt-area-row">' +
            '<span class="dt-level-dot ' + childLevel + '"></span>' +
            '<span class="dt-area-name">' + escHtml(key) + '</span>' +
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

// ── Initialize ────────────────────────────────────────────────────────

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

            document.getElementById('dtLoading').style.display = 'none';
            var container = document.getElementById('dtTreeContainer');
            container.style.display = '';
            container.innerHTML = '';

            var legend = document.createElement('div');
            legend.className = 'dt-level-legend';
            legend.innerHTML =
                '<span class="dt-legend-item"><span class="dt-level-dot l0"></span> Category L0</span>' +
                '<span class="dt-legend-item"><span class="dt-level-dot l1"></span> Category L1</span>' +
                '<span class="dt-legend-item"><span class="dt-level-dot l2"></span> Category L2</span>' +
                '<span class="dt-legend-item"><span class="dt-level-dot pkg"></span> Package</span>' +
                '<span class="dt-legend-item"><span class="dt-level-dot brand"></span> Brand</span>';
            container.appendChild(legend);

            renderTree(container, DT.treeData, 0);

            console.log('[DT] Decision tree built:', data.count, 'products',
                Object.keys(DT.treeData.children).length, 'L0 categories');
        })
        .catch(function(err) {
            document.getElementById('dtLoading').innerHTML =
                '<span style="color:var(--accent-red)">Error: ' + err.message + '</span>';
        });
}

// ── Re-apply highlight after overlay re-render ────────────────────────

var _origRenderAllOverlays = window.renderAllOverlays;
window.renderAllOverlays = function() {
    _origRenderAllOverlays();
    if (DT.activeFilter && DT.matchingProductIds.size > 0) {
        setTimeout(applyTreeHighlight, 10);
    }
};

// ── Panel & tab switching ─────────────────────────────────────────────

function openPanelTab(tab) {
    var panel = document.getElementById('sidePanel');
    panel.classList.add('open');
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

// ── Grid builder (reuse training mode — photos only, no planogram) ────

function buildTrainingGrid(photoNames) {
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
            '</div>';
        grid.appendChild(card);

        var img = document.getElementById('img-' + name);
        img.onload = function() {
            PV.naturalSizes[name] = { w: img.naturalWidth, h: img.naturalHeight };
            fetchPhotoData(name);
            loadedCount++;
            if (loadedCount === photoNames.length) {
                setTimeout(zoomFitAll, 50);
            }
        };
        img.src = '/demo-images/' + name + '.jpg';
    });
}

(function() {
    var origBuildGrid = window.buildGrid;
    window.buildGrid = function(photoNames) {
        if (typeof TRAINING2_MODE !== 'undefined' && TRAINING2_MODE) {
            buildTrainingGrid(photoNames);
        } else if (typeof TRAINING_MODE !== 'undefined' && TRAINING_MODE) {
            origBuildGrid(photoNames);
        } else {
            origBuildGrid(photoNames);
        }
    };
})();

// ── Toolbar & settings ────────────────────────────────────────────────

function toggleSettings(event) {
    event.stopPropagation();
    document.getElementById('settingsMenu').classList.toggle('open');
}

document.querySelector('.settings-btn').addEventListener('click', function(e) {
    e.stopPropagation();
    toggleSettings(e);
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

// ── Grid events (drag, zoom, click) ───────────────────────────────────

document.getElementById('photosGrid').addEventListener('wheel', function(e) {
    e.preventDefault();
    zoomAll(e.deltaY > 0 ? -0.02 : 0.02);
}, { passive: false });

var grid = document.getElementById('photosGrid');

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
    if (PV.drag.active) {
        PV.drag.active = false;
        grid.classList.remove('dragging');
    }
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

// ── Initial load ──────────────────────────────────────────────────────

PV.planogramFacings = {};
PV.salesData = {};

if (PV.photos.length > 0) loadAllPhotos();

setTimeout(initDecisionTree, 300);
