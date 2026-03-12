/* Photo Viewer — SVG overlay rendering and selection highlighting. */

function renderAllOverlays() {
    PV.photos.forEach(name => {
        if (PV.photoData[name] && document.getElementById(`svg-${name}`)) {
            renderOverlay(name);
        }
    });
}

function renderOverlay(name) {
    const data = PV.photoData[name];
    if (!data) return;
    const size = PV.naturalSizes[name];
    if (!size) return;

    const svg = document.getElementById(`svg-${name}`);
    svg.setAttribute('width', size.w);
    svg.setAttribute('height', size.h);
    svg.setAttribute('viewBox', `0 0 ${size.w} ${size.h}`);
    svg.innerHTML = '';

    const showProducts = document.getElementById('showProducts').checked;
    const showShelves = document.getElementById('showShelves').checked;
    const showLabels = document.getElementById('showLabels').checked;

    const statsEl = document.getElementById(`stats-${name}`);
    if (statsEl) {
        const uniqueInPhoto = new Set(data.products.map(p => p.art)).size;
        statsEl.innerHTML = `SKUs: <strong>${uniqueInPhoto}</strong> &nbsp; Facings: <strong>${data.products.length}</strong> &nbsp; Shelves: <strong>${data.shelves.length}</strong>`;
    }

    if (showShelves) {
        const gShelves = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        data.shelves.forEach((s, i) => {
            const y = Math.min(s.y1, s.y2);
            const h = Math.abs(s.y2 - s.y1) || 6;

            const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            rect.setAttribute('x', s.x1);
            rect.setAttribute('y', y - 3);
            rect.setAttribute('width', s.x2 - s.x1);
            rect.setAttribute('height', h + 6);
            rect.setAttribute('fill', 'rgba(0,180,216,0.2)');
            rect.setAttribute('stroke', '#00b4d8');
            rect.setAttribute('stroke-width', '8');
            rect.setAttribute('class', 'bbox-shelf');
            rect.setAttribute('data-shelf-idx', i);
            rect.setAttribute('data-photo', name);
            rect.onclick = () => selectShelf(name, i);
            gShelves.appendChild(rect);

            if (showLabels) {
                const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                txt.setAttribute('x', s.x1 + 8);
                txt.setAttribute('y', y - 8);
                txt.setAttribute('fill', '#00b4d8');
                txt.setAttribute('font-size', '40');
                txt.setAttribute('class', 'bbox-label');
                txt.textContent = `Shelf ${i + 1}`;
                gShelves.appendChild(txt);
            }
        });
        svg.appendChild(gShelves);
    }

    if (showProducts) {
        const gProducts = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        data.products.forEach((p, i) => {
            const color = getBoxColor(p.art);
            const w = p.x2 - p.x1;
            const h = p.y2 - p.y1;

            const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            rect.setAttribute('x', p.x1);
            rect.setAttribute('y', p.y1);
            rect.setAttribute('width', w);
            rect.setAttribute('height', h);
            rect.setAttribute('fill', color + '22');
            rect.setAttribute('stroke', color);
            rect.setAttribute('stroke-width', '6');
            rect.setAttribute('rx', '4');
            rect.setAttribute('class', 'bbox-product');
            rect.setAttribute('data-product-idx', i);
            rect.setAttribute('data-product-id', p._id);
            rect.setAttribute('data-art', p.art);
            rect.setAttribute('data-photo', name);
            rect.style.opacity = (PV.selection.id === p._id && PV.selection.photoName === name) ? '1' : '0.7';
            rect.onclick = (e) => { e.stopPropagation(); selectProduct(name, i); };
            gProducts.appendChild(rect);

            if (showLabels) {
                const labelBg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
                const displayName = p.display_name || p.art;
                const fontSize = Math.min(36, Math.max(16, w * 0.12));
                const labelW = Math.min(w, displayName.length * fontSize * 0.55 + 8);
                const labelH = fontSize + 6;
                labelBg.setAttribute('x', p.x1);
                labelBg.setAttribute('y', p.y1 - labelH);
                labelBg.setAttribute('width', labelW);
                labelBg.setAttribute('height', labelH);
                labelBg.setAttribute('fill', color);
                labelBg.setAttribute('rx', '3');
                labelBg.setAttribute('class', 'bbox-label-bg');
                labelBg.setAttribute('data-art', p.art);
                labelBg.style.pointerEvents = 'none';
                gProducts.appendChild(labelBg);

                const txt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                txt.setAttribute('x', p.x1 + 4);
                txt.setAttribute('y', p.y1 - 5);
                txt.setAttribute('fill', '#fff');
                txt.setAttribute('font-size', fontSize);
                txt.setAttribute('class', 'bbox-label');
                txt.setAttribute('data-art', p.art);
                txt.textContent = displayName;
                gProducts.appendChild(txt);
            }
        });
        svg.appendChild(gProducts);
    }

    highlightSelected();
}

function highlightSelected() {
    const hasSelection = !!PV.selection.art;

    document.querySelectorAll('.bbox-product').forEach(el => {
        const art = el.getAttribute('data-art');
        const origColor = getBoxColor(art);

        if (!hasSelection) {
            el.setAttribute('stroke', origColor);
            el.setAttribute('fill', origColor + '22');
            el.setAttribute('stroke-width', '6');
            el.style.opacity = '0.7';
        } else if (art === PV.selection.art) {
            el.setAttribute('stroke', '#ffd166');
            el.setAttribute('fill', 'rgba(255,209,102,0.15)');
            el.setAttribute('stroke-width', '10');
            el.style.opacity = '1';
        } else {
            el.setAttribute('stroke', '#666');
            el.setAttribute('fill', 'rgba(100,100,100,0.15)');
            el.setAttribute('stroke-width', '4');
            el.style.opacity = '0.4';
        }
    });

    document.querySelectorAll('.bbox-label-bg').forEach(el => {
        const art = el.getAttribute('data-art');
        const origColor = getBoxColor(art);
        if (!hasSelection) {
            el.setAttribute('fill', origColor);
            el.style.opacity = '1';
        } else if (art === PV.selection.art) {
            el.setAttribute('fill', '#ffd166');
            el.style.opacity = '1';
        } else {
            el.setAttribute('fill', '#555');
            el.style.opacity = '0.4';
        }
    });

    document.querySelectorAll('.bbox-label').forEach(el => {
        const art = el.getAttribute('data-art');
        if (!hasSelection || art === PV.selection.art) {
            el.style.opacity = '1';
        } else {
            el.style.opacity = '0.3';
        }
    });

    document.querySelectorAll('.bbox-shelf').forEach(el => {
        const idx = parseInt(el.getAttribute('data-shelf-idx'));
        const photo = el.getAttribute('data-photo');
        const data = PV.photoData[photo];
        if (data) {
            const s = data.shelves[idx];
            if (s._id === PV.selection.id && photo === PV.selection.photoName) {
                el.setAttribute('stroke-width', '12');
                el.setAttribute('fill', 'rgba(0,180,216,0.35)');
            } else {
                el.setAttribute('stroke-width', '8');
                el.setAttribute('fill', 'rgba(0,180,216,0.2)');
            }
        }
    });

    document.querySelectorAll('.product-block[data-art]').forEach(el => {
        const art = el.dataset.art;
        el.classList.remove('realogram-selected', 'realogram-dimmed');
        if (!hasSelection) {
            el.style.opacity = '';
            el.style.filter = '';
        } else if (art === PV.selection.art) {
            el.classList.add('realogram-selected');
        } else {
            el.classList.add('realogram-dimmed');
        }
    });
}
