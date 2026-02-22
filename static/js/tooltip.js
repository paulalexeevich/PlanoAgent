/* TOOLTIP — Product hover tooltip */

function showTooltip(event, product, position) {
    const tt = document.getElementById('tooltip');
    const margin = ((product.price - product.cost) / product.price * 100).toFixed(1);
    const sizeStr = `${dFmt(product.width_in)} x ${dFmt(product.height_in)} x ${dFmt(product.depth_in)}`;
    const volStr = useMetric
        ? `${(product.unit_size_oz * 29.5735).toFixed(0)} ml`
        : `${product.unit_size_oz} oz`;
    tt.innerHTML = `
        <h4>${product.name}</h4>
        <div class="row"><span class="label">Brand</span><span class="value">${product.brand}</span></div>
        <div class="row"><span class="label">Type</span><span class="value">${product.beer_type}</span></div>
        <div class="row"><span class="label">Package</span><span class="value">${product.pack_size}x ${volStr} ${product.package_type}</span></div>
        <div class="row"><span class="label">ABV</span><span class="value">${product.abv}%</span></div>
        <div class="row"><span class="label">Size (${dUnit()})</span><span class="value">${sizeStr}</span></div>
        <div class="row"><span class="label">Price</span><span class="value">${cFmt(product.price)}</span></div>
        <div class="row"><span class="label">Cost</span><span class="value">${cFmt(product.cost)}</span></div>
        <div class="row"><span class="label">Margin</span><span class="value">${margin}%</span></div>
        <div class="row"><span class="label">Facings</span><span class="value">${position.facings_wide}W x ${position.facings_high}H x ${position.facings_deep}D</span></div>
        <div class="row"><span class="label">UPC</span><span class="value">${product.upc}</span></div>
    `;
    tt.classList.add('active');
    moveTooltip(event);
}

function moveTooltip(event) {
    const tt = document.getElementById('tooltip');
    let x = event.clientX + 16;
    let y = event.clientY + 16;
    if (x + 240 > window.innerWidth) x = event.clientX - 250;
    if (y + 200 > window.innerHeight) y = event.clientY - 210;
    tt.style.left = x + 'px';
    tt.style.top = y + 'px';
}

function hideTooltip() {
    document.getElementById('tooltip').classList.remove('active');
}
