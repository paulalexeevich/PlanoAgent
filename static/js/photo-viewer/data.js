/* Photo Viewer — Photo grid building, data fetching, and stats. */

function rebuildPhotoSelect() {
    const sel = document.getElementById('photoSelect');
    sel.innerHTML = PV.photos.map(p => `<option value="${p}">${p}</option>`).join('');
}

function setView(mode) {
    PV.view = mode;
    const viewToggle = event.target.closest('.settings-section').querySelector('.view-toggle');
    const btns = viewToggle.querySelectorAll('button');
    btns.forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    document.getElementById('photoSelect').style.display = mode === 'single' ? 'block' : 'none';
    if (mode === 'single') {
        const sel = document.getElementById('photoSelect').value;
        loadSinglePhoto(sel);
    } else {
        loadAllPhotos();
    }
}

function loadSinglePhoto(name) {
    buildGrid([name]);
}

async function loadAllPhotos() {
    buildGrid(PV.photos);
}

function buildGrid(photoNames) {
    const grid = document.getElementById('photosGrid');
    grid.innerHTML = '';
    let loadedCount = 0;

    photoNames.forEach(name => {
        const card = document.createElement('div');
        card.className = 'photo-card';
        card.id = `card-${name}`;
        card.innerHTML = `
            <div class="photo-header">
                <span class="photo-title">${name}</span>
                <span class="photo-stats" id="stats-${name}">Loading...</span>
            </div>
            <div class="canvas-inner" id="canvas-${name}">
                <img id="img-${name}" alt="${name}">
                <svg id="svg-${name}" xmlns="http://www.w3.org/2000/svg"></svg>
            </div>
            <div class="plano-bay-section">
                <div class="plano-bay-header">
                    <span>Realogram</span>
                </div>
                <div class="planogram-container plano-mini show-dimensions" id="plano-${name}">
                    <div class="plano-loading">Building planogram...</div>
                </div>
            </div>
        `;
        grid.appendChild(card);

        const img = document.getElementById(`img-${name}`);
        img.onload = function() {
            PV.naturalSizes[name] = { w: img.naturalWidth, h: img.naturalHeight };
            fetchPhotoData(name);
            loadedCount++;
            if (loadedCount === photoNames.length) {
                setTimeout(zoomFitAll, 50);
                fetchAndRenderPlanograms();
            }
        };
        img.src = `/demo-images/${name}.jpg`;
    });
}

async function fetchPhotoData(name) {
    if (PV.photoData[name]) {
        renderOverlay(name);
        updateStats();
        return;
    }
    const resp = await fetch(`/api/photo-data/${name}`);
    PV.photoData[name] = await resp.json();
    renderOverlay(name);
    updateStats();
    renderProductList();
    calculateSalesPerMeter();
}

function updateStats() {
    const activePhotos = Object.keys(PV.photoData).filter(n =>
        document.getElementById(`card-${n}`)
    );
    let totalFacings = 0;
    const uniqueArts = new Set();
    activePhotos.forEach(n => {
        const data = PV.photoData[n];
        if (!data) return;
        totalFacings += data.products.length;
        data.products.forEach(p => uniqueArts.add(p.art));
    });
    document.getElementById('statPhotos').textContent = activePhotos.length;
    document.getElementById('statUnique').textContent = uniqueArts.size;
    document.getElementById('statProducts').textContent = totalFacings;
}
