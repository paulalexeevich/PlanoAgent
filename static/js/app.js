/* APP — Initialization, renderAll, glue functions */

function renderAll() {
    buildDtPositionMap();
    updateLayerSelector();
    renderPlanogram();
    renderSummary();
    renderDecisionTree();
    renderJSON();
}

function renderJSON() {
    if (planogramData) {
        document.getElementById('jsonContent').textContent = JSON.stringify(planogramData, null, 2);
    }
}

function toggleJSON() {
    const panel = document.getElementById('jsonPanel');
    panel.classList.toggle('active');
}

function toggleConfig() {
    openEquipmentEditor();
}

document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
    fetchFullCatalog();
    fetchPlanogram();
    document.getElementById('scaleSlider').addEventListener('input', (e) => {
        scale = parseFloat(e.target.value);
        document.getElementById('scaleValue').textContent = scale + 'px/' + dUnit();
        saveSettings();
        if (planogramData) renderPlanogram();
    });
    document.getElementById('eqBays').addEventListener('input', () => {
        if (bayConfigVisible) buildBayConfigTable(true);
    });
    document.addEventListener('click', (e) => {
        const popover = document.getElementById('allBaysPopover');
        const btn = document.getElementById('edAllBaysBtn');
        if (popover && popover.classList.contains('open') && !popover.contains(e.target) && e.target !== btn) {
            toggleAllBaysPopover(false);
        }
    });
    initEditorDragHandlers();
    initEditorScaleSlider();
});
