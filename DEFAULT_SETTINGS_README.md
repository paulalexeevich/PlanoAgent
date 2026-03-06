# Default Settings Configuration

## Summary
Made the following settings default in the Planogram Agent application:

### Changes Made

1. **Data Source**: Supabase (default)
2. **Display Layers**: 
   - Products: ✓ (enabled)
   - Shelves: ✗ (disabled)
   - Labels: ✗ (disabled)
3. **Color Mode**: ₽/meter (price per meter)

### Files Modified

1. **static/js/state.js**
   - Added `dataSource = 'supabase'` (default data source)
   - Added `colorMode = 'price_meter'` (default color mode)
   - Added `displayLayers = { products: true, shelves: false, labels: false }`

2. **static/js/settings.js**
   - Added `setDataSource()` function
   - Added `setColorMode()` function
   - Added `setDisplayLayer()` function
   - Updated `openSettings()` to load new settings
   - Updated `saveSettings()` to persist new settings
   - Updated `loadSettings()` to restore new settings from localStorage

3. **static/js/init-defaults.js** (NEW)
   - Automatically initializes default settings on first load
   - Sets all default values to localStorage if not already present

4. **templates/index.html**
   - Added "Data Source" section to settings overlay
   - Added "Display Layers" section with checkboxes for Products, Shelves, Labels
   - Added "Color Mode" section with Colors/₽meter options
   - Included init-defaults.js script to load before other scripts

### How It Works

1. On first page load, `init-defaults.js` checks if settings exist in localStorage
2. If no settings found, it creates them with your preferred defaults:
   - Data Source: Supabase
   - Color Mode: ₽/meter
   - Display Layers: Products only
3. These settings are then loaded by `settings.js` on every subsequent page load
4. Settings persist across browser sessions via localStorage
5. Users can still change settings via the Settings overlay (⚙ icon in header)

### Testing

The application is currently running at http://localhost:5001

To test:
1. Clear localStorage in browser dev tools (optional, to see fresh defaults)
2. Reload the page
3. Click the ⚙ Settings icon in the header
4. Verify that:
   - Data Source is set to "Supabase"
   - Products layer is checked
   - Shelves and Labels are unchecked
   - Color Mode is set to "₽/meter"

### Notes

- Settings are saved automatically when changed
- Settings persist in browser localStorage
- First-time users will see these defaults immediately
- Existing users will keep their current settings (unless they clear localStorage)
