/* Photo Viewer — Global state namespace.
 * Loaded first. PV.photos is set from the Jinja template via _PHOTOS_INIT. */

const PV = {
    photos: (typeof _PHOTOS_INIT !== 'undefined') ? _PHOTOS_INIT : [],
    photoData: {},
    scales: {},
    naturalSizes: {},
    planogramFacings: {},
    salesData: {},
    view: 'all',
    selection: { id: null, photoName: null, art: null },
    filter: 'all',
    globalScale: null,
    productColors: {},
    COLOR_PALETTE: [
        '#e94560','#00b4d8','#90be6d','#f9c74f','#f8961e',
        '#43aa8b','#577590','#f3722c','#4cc9f0','#7209b7',
        '#3a86a7','#fb5607','#ff006e','#8338ec','#06d6a0',
        '#118ab2','#ef476f','#ffd166','#073b4c','#06aed5'
    ],
    colorMode: 'default',
    salesPerMeter: { map: {}, avg: 0 },
    activeTab: 'actions',
    actions: { data: [], loaded: false, filter: 'all' },
    recog: { planogramData: null, productsMap: {}, bayMap: {} },
    drag: { active: false, startX: 0, startY: 0, scrollX: 0, scrollY: 0, distance: 0 },
    planoRenderTimer: null,
};

function getColorForArt(art) {
    if (!PV.productColors[art]) {
        const idx = Object.keys(PV.productColors).length % PV.COLOR_PALETTE.length;
        PV.productColors[art] = PV.COLOR_PALETTE[idx];
    }
    return PV.productColors[art];
}

function getBoxColor(art) {
    if (PV.colorMode === 'salesPerMeter') {
        const data = PV.salesPerMeter.map[art];
        if (data) return data.color;
        return '#888888';
    }
    return getColorForArt(art);
}
