/* Photo Viewer — Product list rendering and filtering. */

function getProductStatus(art, photoFacings) {
    const pf = PV.planogramFacings[art];
    if (!pf) return 'not-in-plano';
    if (photoFacings === 0) return 'out-of-shelf';
    const plano = pf.facings_wide;
    if (photoFacings < plano) return 'less';
    if (photoFacings === plano) return 'equal';
    return 'more';
}

function renderProductList() {
    const artCounts = {};
    PV.photos.forEach(name => {
        const data = PV.photoData[name];
        if (!data) return;
        data.products.forEach(p => {
            const key = p.art;
            if (!artCounts[key]) {
                artCounts[key] = {
                    count: 0,
                    display_name: p.display_name,
                    miniature_url: p.miniature_url || '',
                    brand_name: p.brand_name || '',
                    photos: new Set(),
                    firstPhoto: name,
                    firstIdx: data.products.indexOf(p),
                };
            }
            artCounts[key].count++;
            artCounts[key].photos.add(name);
        });
    });

    Object.keys(PV.planogramFacings).forEach(art => {
        if (!artCounts[art]) {
            const pf = PV.planogramFacings[art];
            artCounts[art] = {
                count: 0,
                display_name: pf.name || art,
                miniature_url: pf.image_url || '',
                brand_name: pf.brand || '',
                photos: new Set(),
                firstPhoto: '',
                firstIdx: -1,
                isOutOfShelf: true,
            };
        }
    });

    const statusOrder = { 'not-in-plano': 0, 'out-of-shelf': 1, 'less': 2, 'more': 3, 'equal': 4 };
    const items = Object.entries(artCounts)
        .map(([art, info]) => {
            const status = getProductStatus(art, info.count);
            return [art, info, status];
        })
        .sort((a, b) => {
            const sa = statusOrder[a[2]] ?? 5;
            const sb = statusOrder[b[2]] ?? 5;
            if (sa !== sb) return sa - sb;
            return b[1].count - a[1].count;
        });

    const counts = { all: items.length };
    items.forEach(([, , status]) => { counts[status] = (counts[status] || 0) + 1; });
    document.getElementById('filterCounts').innerHTML =
        `<span style="color:#ef4444">${counts['not-in-plano']||0} not in plano</span> · ` +
        `<span style="color:#f59e0b">${counts['less']||0} less</span> · ` +
        `<span style="color:#34d399">${counts['equal']||0} equal</span> · ` +
        `<span style="color:#4a9eff">${counts['more']||0} more</span> · ` +
        `<span style="color:#facc15">${counts['out-of-shelf']||0} out of shelf</span>`;

    const container = document.getElementById('productListItems');
    container.innerHTML = items.map(([art, info, status]) => {
        const thumb = info.miniature_url
            ? `<img class="thumb" src="${info.miniature_url}" alt="" onerror="this.style.display='none'">`
            : `<span class="color-dot" style="background:${getBoxColor(art)}"></span>`;
        const pf = PV.planogramFacings[art];
        const planoFacings = pf ? pf.facings_wide : 0;
        const photoFacings = info.count;

        let badge = '';
        if (status === 'not-in-plano') {
            badge = `<span class="tag-alert">Not in plano</span><span class="tag-photo-f">S:${photoFacings}</span>`;
        } else if (status === 'out-of-shelf') {
            badge = `<span class="tag-oos">Out of shelf</span><span class="tag-plano">P:${planoFacings}</span>`;
        } else {
            badge = `<span class="tag-plano">P:${planoFacings}</span><span class="tag-photo-f">S:${photoFacings}</span>`;
        }

        const cssClass = status === 'not-in-plano' ? ' not-in-plano' : status === 'out-of-shelf' ? ' out-of-shelf' : '';
        const clickHandler = info.firstPhoto
            ? `onclick="selectByArt('${art}')"`
            : info.isOutOfShelf
                ? `onclick="selectOutOfShelfProduct('${art}')"`
                : '';

        return `
            <div class="product-list-item${cssClass}" data-art="${art}" data-status="${status}" data-photo="${info.firstPhoto}" ${clickHandler}>
                ${thumb}
                <span style="flex:1">
                    ${info.display_name}${info.brand_name ? `<br><span style="font-size:9px;color:#888">${info.brand_name}</span>` : ''}
                    <br>${badge}
                </span>
            </div>
        `;
    }).join('');

    applyFilter();
}

function setFilter(filter) {
    PV.filter = filter;
    document.querySelectorAll('#filterBar .filter-btn').forEach(b => {
        b.classList.toggle('active', b.getAttribute('data-filter') === filter);
    });
    applyFilter();
}

function applyFilter() {
    const q = document.getElementById('searchInput').value.toLowerCase();
    document.querySelectorAll('.product-list-item').forEach(el => {
        const status = el.getAttribute('data-status');
        const text = el.textContent.toLowerCase();
        const matchesFilter = PV.filter === 'all' || status === PV.filter;
        const matchesSearch = !q || text.includes(q);
        el.style.display = (matchesFilter && matchesSearch) ? '' : 'none';
    });
}

function selectByArt(art) {
    for (const name of PV.photos) {
        const data = PV.photoData[name];
        if (!data) continue;
        const idx = data.products.findIndex(p => p.art === art);
        if (idx >= 0) {
            selectProduct(name, idx);
            return;
        }
    }
}

function filterProductList() {
    applyFilter();
}
