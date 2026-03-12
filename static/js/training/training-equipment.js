/* Training — Equipment validation: compare recognition shelf counts with Supabase equipment config. */

var TrainingEquipment = (function() {
    var storeEquipment = null;
    var shelfCounts = {};

    function fetchEquipmentAndShelves() {
        return Promise.all([
            fetch('/api/store-equipment').then(r => r.json()),
            Promise.all(PV.photos.map(name =>
                fetch('/api/photo-data/' + name).then(r => r.json()).then(data => ({
                    name: name,
                    shelfCount: (data.shelves || []).length,
                    productCount: (data.products || []).filter(p => !p.is_duplicated).length
                }))
            ))
        ]).then(function(results) {
            var eqData = results[0];
            var photoResults = results[1];

            storeEquipment = (eqData.status === 'success' && eqData.equipment) ? eqData.equipment : null;
            shelfCounts = {};
            photoResults.forEach(function(r) { shelfCounts[r.name] = r; });

            return { equipment: storeEquipment, photos: photoResults };
        });
    }

    function validate() {
        return fetchEquipmentAndShelves().then(function(data) {
            if (!data.equipment) {
                return {
                    success: false,
                    error: 'No equipment configuration found in Supabase. Please configure store equipment first.',
                    rows: []
                };
            }

            var eq = data.equipment;
            var baysConfig = eq.bays_config || [];
            var defaultShelves = eq.default_num_shelves || 7;
            var sortedPhotos = data.photos.sort(function(a, b) { return a.name.localeCompare(b.name); });

            var rows = sortedPhotos.map(function(photo, idx) {
                var expectedShelves = defaultShelves;
                if (baysConfig.length > idx && baysConfig[idx].num_shelves) {
                    expectedShelves = baysConfig[idx].num_shelves;
                }
                var match = photo.shelfCount === expectedShelves;
                return {
                    bayNumber: idx + 1,
                    photoName: photo.name,
                    recognitionShelves: photo.shelfCount,
                    equipmentShelves: expectedShelves,
                    productCount: photo.productCount,
                    match: match,
                    dimensionSource: match ? 'Equipment (stable)' : 'Recognition (pixel-based)'
                };
            });

            var allMatch = rows.every(function(r) { return r.match; });
            return {
                success: true,
                allMatch: allMatch,
                equipment: {
                    name: eq.name || 'Store Equipment',
                    type: eq.equipment_type || 'gondola',
                    numBays: eq.num_bays || sortedPhotos.length,
                    bayWidthCm: eq.bay_width_cm,
                    bayHeightCm: eq.bay_height_cm,
                    defaultShelves: defaultShelves
                },
                rows: rows
            };
        });
    }

    function renderResult(container, result) {
        if (!result.success) {
            container.innerHTML =
                '<div class="eq-summary has-mismatch">' + result.error + '</div>';
            return;
        }

        var html = '<table class="eq-validation-table">' +
            '<thead><tr>' +
            '<th>Bay</th><th>Photo</th><th>Detected</th><th>Expected</th><th>Source</th>' +
            '</tr></thead><tbody>';

        result.rows.forEach(function(row) {
            var cls = row.match ? 'match' : 'mismatch';
            var icon = row.match ? '&#10003;' : '&#10007;';
            html += '<tr>' +
                '<td>' + row.bayNumber + '</td>' +
                '<td>' + row.photoName + '</td>' +
                '<td class="' + cls + '"><span class="eq-status-icon">' + icon + '</span>' + row.recognitionShelves + '</td>' +
                '<td>' + row.equipmentShelves + '</td>' +
                '<td style="font-size:10px;color:var(--text-secondary)">' + row.dimensionSource + '</td>' +
                '</tr>';
        });

        html += '</tbody></table>';

        if (result.allMatch) {
            html += '<div class="eq-summary all-match">' +
                'All bays match equipment configuration. Stable dimensions will be used.' +
                '</div>';
        } else {
            var matchCount = result.rows.filter(function(r) { return r.match; }).length;
            html += '<div class="eq-summary has-mismatch">' +
                matchCount + '/' + result.rows.length + ' bays match. ' +
                'Mismatched bays will use pixel-based dimensions from recognition.' +
                '</div>';
        }

        container.innerHTML = html;
    }

    return { validate: validate, renderResult: renderResult };
})();
