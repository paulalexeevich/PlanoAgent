/* COMPARE — Algorithm vs AI comparison modal */

let lastCompareData = null;

function showCompareModal(comparison) {
    const algo = comparison.algorithm;
    const ai = comparison.ai;
    const tbody = document.getElementById('compareBody');

    const rows = [
        ['Fill %', algo.fill_pct + '%', ai.fill_pct + '%', 'high'],
        ['Products', algo.products, ai.products, 'high'],
        ['Facings', algo.facings, ai.facings, 'high'],
        ['Decision Tree', algo.compliance != null ? algo.compliance.toFixed(1) + '%' : 'N/A',
            ai.compliance != null ? ai.compliance.toFixed(1) + '%' : 'N/A', 'high'],
        ['Total time', formatMs(algo.time_ms), formatMs(ai.time_ms), 'low'],
        ['Phase 1+2', formatMs(algo.timings.phase12_ms), formatMs(ai.timings.phase12_ms), 'low'],
        ['Placement', formatMs(algo.timings.rule_based_ms || 0), formatMs(ai.timings.ai_call_ms || 0), 'low'],
        ['Post-processing', formatMs(algo.timings.postprocess_ms), formatMs(ai.timings.postprocess_ms), 'low'],
    ];

    tbody.innerHTML = rows.map(([label, aVal, iVal, mode]) => {
        const aNum = parseFloat(aVal);
        const iNum = parseFloat(iVal);
        let aClass = '', iClass = '';
        if (!isNaN(aNum) && !isNaN(iNum) && aNum !== iNum) {
            if (mode === 'high') {
                aClass = aNum > iNum ? 'winner' : 'loser';
                iClass = iNum > aNum ? 'winner' : 'loser';
            } else {
                aClass = aNum < iNum ? 'winner' : 'loser';
                iClass = iNum < aNum ? 'winner' : 'loser';
            }
        }
        return `<tr><td>${label}</td><td class="${aClass}">${aVal}</td><td class="${iClass}">${iVal}</td></tr>`;
    }).join('');

    document.getElementById('compareOverlay').classList.add('active');
}

async function pickCompareResult(choice) {
    closeCompare();
    document.getElementById('fillMode').value = choice;
    await fillProducts();
}

function closeCompare() {
    document.getElementById('compareOverlay').classList.remove('active');
    setFillLoading(false);
}
