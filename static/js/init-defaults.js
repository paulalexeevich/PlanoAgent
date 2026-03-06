/* INIT DEFAULTS — Set default settings on first load */

(function initDefaults() {
    const existing = localStorage.getItem('planogram_settings');
    if (!existing) {
        // First time load - set defaults
        const defaults = {
            useMetric: false,
            currency: 'USD',
            fillMode: 'algorithm',
            showDimensions: false,
            scale: 5,
            editorScale: 5,
            dataSource: 'supabase',
            colorMode: 'price_meter',
            displayLayers: {
                products: true,
                shelves: false,
                labels: false
            }
        };
        localStorage.setItem('planogram_settings', JSON.stringify(defaults));
        console.log('[init-defaults] Set default settings:', defaults);
    }
})();
