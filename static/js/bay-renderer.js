/* BAY RENDERER — Shared component for rendering planogram bays and shelves.
 *
 * Used by both the main dashboard visualization and the equipment editor.
 * Provides consistent layout with configurable scale, spacing, and hooks
 * for consumer-specific content (products, drag handles, etc.).
 *
 * Config:
 *   container   — target DOM element
 *   scale       — pixels per inch (e.g. 5)
 *   bayGap      — px between non-glued bays (default 4)
 *   gluedGap    — px between glued bays (default 0, negative for overlap)
 *   bays        — normalized bay array (use normalizeDashboard / normalizeEditor)
 *
 * Hooks (all optional):
 *   onHeader(headerEl, titleEl, bay, idx)
 *   onShelf(shelfEl, shelf, si, bay, idx)
 *   onBody(bodyEl, bay, idx)
 *   onDecorations(bayEl, wrapperEl, bay, idx)
 *   onAfterBay(container, bay, idx, isLast)
 */

const BayRenderer = {

    SHELF_BASE: 6,
    SHELF_THICKNESS: 1,

    render(config) {
        const {
            container,
            scale,
            bayGap   = 4,
            gluedGap = 0,
            bays,
            bayClass     = '',
            wrapperClass = '',
            onHeader,
            onShelf,
            onBody,
            onDecorations,
            onAfterBay,
        } = config;

        container.innerHTML = '';
        if (!bays || bays.length === 0) return;

        bays.forEach((bay, idx) => {
            const prevBay  = idx > 0 ? bays[idx - 1] : null;
            const gluedToPrev = prevBay && prevBay.glued_right;
            const isLast   = idx === bays.length - 1;

            const wrapper = document.createElement('div');
            wrapper.className = ('br-bay-wrapper' + (wrapperClass ? ' ' + wrapperClass : ''));
            wrapper.dataset.idx = idx;
            wrapper.style.width = (bay.width_in * scale) + 'px';
            wrapper.style.marginLeft = idx === 0
                ? '0'
                : (gluedToPrev ? gluedGap : bayGap) + 'px';

            let cls = 'br-bay';
            if (gluedToPrev)    cls += ' br-bay-glued-left';
            if (bay.glued_right) cls += ' br-bay-glued-right';
            if (bayClass)       cls += ' ' + bayClass;

            const bayEl = document.createElement('div');
            bayEl.className = cls;
            bayEl.style.width = (bay.width_in * scale) + 'px';

            const header = document.createElement('div');
            header.className = 'br-bay-header';
            const title = document.createElement('span');
            title.className = 'br-bay-title';
            title.textContent = 'Bay ' + (bay.bay_number || idx + 1);
            header.appendChild(title);
            if (onHeader) onHeader(header, title, bay, idx);
            bayEl.appendChild(header);

            const body = document.createElement('div');
            body.className = 'br-bay-body';
            body.style.height = (bay.height_in * scale) + 'px';
            body.style.width  = (bay.width_in  * scale) + 'px';

            const sorted = [...bay.shelves].sort((a, b) => a.y_position - b.y_position);
            sorted.forEach((shelf, si) => {
                const shelfEl = document.createElement('div');
                shelfEl.className = 'br-shelf';
                shelfEl.style.height = (shelf.height_in * scale) + 'px';
                shelfEl.style.bottom = (shelf.y_position * scale) + 'px';

                const label = document.createElement('span');
                label.className = 'br-shelf-label';
                label.textContent = 'S' + shelf.shelf_number + ' \u2014 ' + dFmt(shelf.height_in);
                shelfEl.appendChild(label);

                if (onShelf) onShelf(shelfEl, shelf, si, bay, idx);
                body.appendChild(shelfEl);
            });

            if (onBody) onBody(body, bay, idx);
            bayEl.appendChild(body);

            const footer = document.createElement('div');
            footer.className = 'br-bay-footer';
            footer.textContent = dFmt(bay.width_in);
            bayEl.appendChild(footer);

            if (onDecorations) onDecorations(bayEl, wrapper, bay, idx);

            wrapper.appendChild(bayEl);
            container.appendChild(wrapper);

            if (onAfterBay) onAfterBay(container, bay, idx, isLast);
        });
    },

    normalizeDashboard(equipment) {
        if (!equipment || !equipment.bays) return [];
        return equipment.bays.map(bay => ({
            bay_number:  bay.bay_number,
            width_in:    bay.width_in,
            height_in:   bay.height_in,
            depth_in:    bay.depth_in,
            glued_right: !!bay.glued_right,
            shelves: (bay.shelves || []).map(s => ({
                shelf_number: s.shelf_number,
                y_position:   s.y_position,
                height_in:    s.height_in,
                positions:    s.positions || [],
            })),
        }));
    },

    normalizeEditor(editorBays, heightIn) {
        if (!editorBays) return [];
        const base = this.SHELF_BASE;
        const thick = this.SHELF_THICKNESS;

        return editorBays.map((bay, idx) => {
            const numShelves = bay.num_shelves || 5;
            const clearances = bay.shelf_clearances;
            const shelves = [];

            if (clearances && clearances.length > 0) {
                let yPos = base;
                clearances.forEach((h, si) => {
                    shelves.push({ shelf_number: si + 1, y_position: yPos, height_in: h });
                    yPos += h + thick;
                });
            } else {
                const shelfH = (heightIn - base - numShelves * thick) / numShelves;
                let yPos = base;
                for (let si = 0; si < numShelves; si++) {
                    shelves.push({ shelf_number: si + 1, y_position: yPos, height_in: shelfH });
                    yPos += shelfH + thick;
                }
            }

            return {
                bay_number:  idx + 1,
                width_in:    bay.width_in,
                height_in:   heightIn,
                glued_right: !!bay.glued_right,
                shelves,
                _numShelves: numShelves,
            };
        });
    },
};
