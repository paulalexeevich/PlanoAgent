/* Training — Initialization: step wizard, panel, events, data loading.
 * Loaded last — all other modules (photo-viewer + training-equipment) must be available. */

var Training = { step: 1 };

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
    document.getElementById('tabTraining').style.display = tab === 'training' ? '' : 'none';
    document.getElementById('tabAnalytics').style.display = tab === 'analytics' ? '' : 'none';
}

function setTrainingStep(step) {
    Training.step = step;

    document.getElementById('step1Indicator').className = step >= 1 ? (step > 1 ? 'step completed' : 'step active') : 'step';
    document.getElementById('step2Indicator').className = step >= 2 ? 'step active' : 'step';

    var step1El = document.getElementById('trainStep1');
    var step2El = document.getElementById('trainStep2');

    if (step > 1) {
        step1El.classList.remove('active');
        step1El.classList.add('completed');
        step2El.classList.remove('locked');
        step2El.classList.add('active');
        document.getElementById('btnBuildRealogram').disabled = false;
    }
}

// ── Step 1: Validate Equipment ─────────────────────────────────────────

document.getElementById('btnValidateEquipment').addEventListener('click', function() {
    var btn = this;
    var label = document.getElementById('validateLabel');
    var spinner = document.getElementById('validateSpinner');
    var resultEl = document.getElementById('equipmentResult');

    btn.disabled = true;
    label.textContent = 'Validating...';
    spinner.style.display = '';
    resultEl.innerHTML = '';

    TrainingEquipment.validate()
        .then(function(result) {
            TrainingEquipment.renderResult(resultEl, result);
            if (result.success) {
                setTrainingStep(2);
            }
        })
        .catch(function(err) {
            resultEl.innerHTML = '<div class="eq-summary has-mismatch">Error: ' + err.message + '</div>';
        })
        .finally(function() {
            btn.disabled = false;
            label.textContent = 'Validate Equipment';
            spinner.style.display = 'none';
        });
});

// ── Step 2: Build Realogram ────────────────────────────────────────────

document.getElementById('btnBuildRealogram').addEventListener('click', function() {
    var btn = this;
    var label = document.getElementById('buildLabel');
    var spinner = document.getElementById('buildSpinner');
    var resultEl = document.getElementById('buildResult');

    btn.disabled = true;
    label.textContent = 'Building...';
    spinner.style.display = '';
    resultEl.innerHTML = '';

    fetch('/api/build-from-recognition', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}'
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.status !== 'success' || !data.planogram) {
            resultEl.innerHTML = '<div class="eq-summary has-mismatch">Build failed: ' + (data.error || 'Unknown error') + '</div>';
            return;
        }

        _applyPlanogramData(data);

        var plano = data.planogram;
        var numBays = plano.equipment ? plano.equipment.bays.length : 0;
        var numProducts = (plano.products || []).length;
        var totalFacings = 0;
        if (plano.equipment) {
            plano.equipment.bays.forEach(function(bay) {
                bay.shelves.forEach(function(shelf) {
                    shelf.positions.forEach(function(pos) {
                        if (!pos._phantom) totalFacings += (pos.facings_wide || 1);
                    });
                });
            });
        }

        resultEl.innerHTML =
            '<div class="eq-summary all-match">Realogram built successfully!</div>' +
            '<div class="build-stats">' +
            '<div class="build-stat">Bays<strong>' + numBays + '</strong></div>' +
            '<div class="build-stat">Products<strong>' + numProducts + '</strong></div>' +
            '<div class="build-stat">Facings<strong>' + totalFacings + '</strong></div>' +
            '</div>';

        document.getElementById('step2Indicator').classList.add('completed');
    })
    .catch(function(err) {
        resultEl.innerHTML = '<div class="eq-summary has-mismatch">Error: ' + err.message + '</div>';
    })
    .finally(function() {
        btn.disabled = false;
        label.textContent = 'Build Realogram';
        spinner.style.display = 'none';
    });
});

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

document.getElementById('searchInput').addEventListener('input', filterProductList);

document.getElementById('filterBar').addEventListener('click', function(e) {
    var btn = e.target.closest('[data-filter]');
    if (btn) setFilter(btn.dataset.filter);
});

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

// ── Training-specific grid builder (empty planograms) ─────────────────

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
            '</div>' +
            '<div class="plano-bay-section">' +
            '<div class="plano-bay-header"><span>Realogram</span></div>' +
            '<div class="planogram-container plano-mini show-dimensions" id="plano-' + name + '">' +
            '<div class="plano-empty-state">Complete Steps 1 &amp; 2 to build</div>' +
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
            }
        };
        img.src = '/demo-images/' + name + '.jpg';
    });
}

// Override data.js buildGrid for training mode (empty planograms until step 2)
(function() {
    var origBuildGrid = window.buildGrid;
    window.buildGrid = function(photoNames) {
        if (typeof TRAINING_MODE !== 'undefined' && TRAINING_MODE) {
            buildTrainingGrid(photoNames);
        } else {
            origBuildGrid(photoNames);
        }
    };
})();

// ── Initial load ──────────────────────────────────────────────────────

PV.planogramFacings = {};
PV.salesData = {};

fetch('/api/planogram-facings')
    .then(function(r) { return r.json(); })
    .then(function(facings) {
        PV.planogramFacings = facings || {};
        console.log('[training] Loaded planogram facings:', Object.keys(PV.planogramFacings).length);
    })
    .catch(function(err) {
        console.warn('[training] Could not load planogram facings:', err);
    });

if (PV.photos.length > 0) loadAllPhotos();
