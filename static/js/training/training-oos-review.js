(function() {
    'use strict';

    const loadBtn = document.getElementById('btnLoadOosReview');
    const loadLabel = document.getElementById('oosReviewLabel');
    const loadSpinner = document.getElementById('oosReviewSpinner');
    const resultEl = document.getElementById('oosReviewResult');
    const listEl = document.getElementById('oosReviewList');
    const completeBtn = document.getElementById('btnCompleteOosReview');

    if (!loadBtn || !listEl) return;

    function unlockStep3() {
        const stepEl = document.getElementById('trainStep3');
        const ind = document.getElementById('step3Indicator');
        if (stepEl) {
            stepEl.classList.remove('locked');
            stepEl.classList.add('active');
        }
        if (ind) ind.classList.add('active');
        loadBtn.disabled = false;
    }

    function completeStep3() {
        const step3 = document.getElementById('trainStep3');
        const ind3 = document.getElementById('step3Indicator');
        const step4 = document.getElementById('trainStep4');
        const ind4 = document.getElementById('step4Indicator');
        const runBtn = document.getElementById('btnProposedPlanogram');
        if (step3) step3.classList.add('completed');
        if (ind3) ind3.classList.add('completed');
        if (step4) {
            step4.classList.remove('locked');
            step4.classList.add('active');
        }
        if (ind4) ind4.classList.add('active');
        if (runBtn) runBtn.disabled = false;
        if (typeof enableStepCollapse === 'function') enableStepCollapse(3);
    }

    async function patchActionStatus(actionId, newStatus) {
        const resp = await fetch('/api/actions/' + actionId, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus }),
        });
        const data = await resp.json();
        if (data.status !== 'success') {
            throw new Error(data.error || 'Failed to update status');
        }
    }

    function renderActions(actions) {
        const oos = actions.filter(a => (a.status || 'pending') !== 'resolved');
        const excludedCount = oos.filter(a => a.status === 'out_of_stock').length;
        const activeCount = oos.length - excludedCount;

        resultEl.innerHTML =
            `<div class="eq-summary all-match">Ready for optimization: ${activeCount}</div>` +
            `<div class="build-stats">` +
            `<div class="build-stat">Total<strong>${oos.length}</strong></div>` +
            `<div class="build-stat">Will install<strong>${activeCount}</strong></div>` +
            `<div class="build-stat">Out of stock<strong>${excludedCount}</strong></div>` +
            `</div>`;

        listEl.innerHTML = oos.map((a, i) => {
            const isOos = a.status === 'out_of_stock';
            const btnText = isOos ? 'Undo Out-of-stock' : 'Mark Out-of-stock';
            const cls = isOos ? 'oos-excluded' : 'oos-active';
            return `
                <div class="oos-item ${cls}" data-action-id="${a.id}">
                    <div class="oos-rank">${i + 1}</div>
                    <div class="oos-body">
                        <div class="oos-name">${a.product_name || a.tiny_name || a.product_code || 'Unknown'}</div>
                        <div class="oos-meta">
                            ${a.brand ? `<span class="tag-brand">${a.brand}</span>` : ''}
                            <span class="pal-sale">${Math.round(parseFloat(a.avg_sale_amount || 0)).toLocaleString('ru-RU')} ₽/wk</span>
                            <span class="pal-facings">${a.planogram_facings || 1} facings</span>
                            ${isOos ? '<span class="oos-state">excluded</span>' : '<span class="oos-state">will install</span>'}
                        </div>
                    </div>
                    <button class="oos-toggle-btn" data-action-id="${a.id}" data-next-status="${isOos ? 'pending' : 'out_of_stock'}">${btnText}</button>
                </div>
            `;
        }).join('');
        listEl.style.display = '';
        completeBtn.style.display = '';
    }

    async function loadOosActions() {
        loadBtn.disabled = true;
        loadLabel.textContent = 'Loading...';
        loadSpinner.style.display = '';
        try {
            const resp = await fetch('/api/actions');
            const data = await resp.json();
            if (data.status !== 'success') throw new Error(data.error || 'Failed to load actions');
            renderActions(data.actions || []);
        } catch (e) {
            resultEl.innerHTML = `<div class="eq-summary has-mismatch">Error: ${e.message}</div>`;
        } finally {
            loadBtn.disabled = false;
            loadLabel.textContent = 'Reload Out-of-Shelf Products';
            loadSpinner.style.display = 'none';
        }
    }

    loadBtn.addEventListener('click', loadOosActions);

    listEl.addEventListener('click', async (e) => {
        const btn = e.target.closest('.oos-toggle-btn');
        if (!btn) return;
        const actionId = btn.getAttribute('data-action-id');
        const nextStatus = btn.getAttribute('data-next-status');
        btn.disabled = true;
        try {
            await patchActionStatus(actionId, nextStatus);
            await loadOosActions();
        } catch (err) {
            btn.disabled = false;
            resultEl.innerHTML = `<div class="eq-summary has-mismatch">Update failed: ${err.message}</div>`;
        }
    });

    completeBtn.addEventListener('click', completeStep3);

    const step2Ind = document.getElementById('step2Indicator');
    if (step2Ind) {
        if (step2Ind.classList.contains('completed')) {
            unlockStep3();
        } else {
            const obs = new MutationObserver(function() {
                if (step2Ind.classList.contains('completed')) {
                    unlockStep3();
                    obs.disconnect();
                }
            });
            obs.observe(step2Ind, { attributes: true, attributeFilter: ['class'] });
        }
    }
})();
