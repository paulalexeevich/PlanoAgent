/* BAY CONFIG — Per-bay configuration form */

let bayConfigVisible = false;

function setBayMode(mode) {
    bayConfigVisible = (mode === 'perbay');
    document.getElementById('modeSimpleBtn').classList.toggle('active', !bayConfigVisible);
    document.getElementById('modePerBayBtn').classList.toggle('active', bayConfigVisible);
    document.getElementById('fgShelves').style.display = bayConfigVisible ? 'none' : '';
    document.getElementById('fgWidth').style.display   = bayConfigVisible ? 'none' : '';
    const section = document.getElementById('bayConfigSection');
    section.classList.toggle('open', bayConfigVisible);
    if (bayConfigVisible) buildBayConfigTable();
}

function buildBayConfigTable(keepExisting) {
    const numBays = parseInt(document.getElementById('eqBays').value) || 1;
    const defWidth = document.getElementById('eqWidth').value;
    const defShelves = document.getElementById('eqShelves').value;

    const tbody = document.getElementById('bayConfigTableBody');
    const existingRows = Array.from(tbody.querySelectorAll('.bay-config-row'));

    tbody.innerHTML = '';
    for (let i = 0; i < numBays; i++) {
        const old = existingRows[i];
        const w = old ? old.querySelector('.bay-width-input').value : defWidth;
        const s = old ? old.querySelector('.bay-shelves-input').value : defShelves;
        const h = old ? old.querySelector('.bay-heights-input').value : '';

        const wMin = useMetric ? 30 : 12;
        const wMax = useMetric ? 305 : 120;
        const tr = document.createElement('tr');
        tr.className = 'bay-config-row';
        tr.innerHTML = `
            <td class="bay-num">B${i + 1}</td>
            <td><input type="number" class="bay-width-input" value="${w}" min="${wMin}" max="${wMax}" step="1"></td>
            <td><input type="number" class="bay-shelves-input" value="${s}" min="1" max="12"></td>
            <td><input type="text" class="bay-heights-input" value="${h}" placeholder="auto" title="Clearance height per shelf, e.g. 12,14,16,14,12"></td>
        `;
        tbody.appendChild(tr);
    }
}

function resetBayConfigDefaults() {
    document.getElementById('bayConfigTableBody').innerHTML = '';
    buildBayConfigTable();
}

function collectBaysConfig() {
    if (!bayConfigVisible) return null;
    const rows = document.querySelectorAll('#bayConfigTableBody .bay-config-row');
    if (rows.length === 0) return null;

    return Array.from(rows).map(row => {
        const widthRaw = parseFloat(row.querySelector('.bay-width-input').value);
        const shelves = parseInt(row.querySelector('.bay-shelves-input').value);
        const heightsStr = row.querySelector('.bay-heights-input').value.trim();
        const width = isNaN(widthRaw) ? NaN : (useMetric ? +(widthRaw / IN_TO_CM).toFixed(2) : widthRaw);
        const clearances = heightsStr
            ? heightsStr.split(',').map(h => {
                const n = parseFloat(h.trim());
                if (isNaN(n) || n <= 0) return null;
                return useMetric ? +(n / IN_TO_CM).toFixed(2) : n;
            }).filter(h => h !== null)
            : null;
        return {
            width_in: isNaN(width) ? null : width,
            num_shelves: isNaN(shelves) ? null : shelves,
            shelf_clearances: (clearances && clearances.length > 0) ? clearances : null,
        };
    });
}
