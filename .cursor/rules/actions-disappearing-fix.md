# Actions Disappearing Issue - Root Cause & Fix

## Problem
Actions loaded from `/api/actions` were disappearing from the Photo Viewer UI intermittently.

## Root Cause Analysis

The issue was caused by **silent error handling** in the actions pre-load code:

```javascript
// Pre-load actions count for the badge
fetch('/api/actions').then(r => r.json()).then(data => {
    if (data.status === 'success') {
        actionsData = data.actions;
        actionsLoaded = true;
        const badge = document.getElementById('actionsBadge');
        badge.textContent = data.actions.length;
    }
}).catch(() => {});  // ❌ Silent error - no logging or state reset
```

### The Problem Flow:

1. **Initial page load** attempts to pre-load actions data
2. **Network error or API error** occurs (e.g., timeout, server issue, RLS policy)
3. **Error is silently caught** with empty catch block
4. `actionsData` remains empty array `[]`
5. `actionsLoaded` flag is **not reset to false** on error
6. When user clicks Actions button:
   - Code checks `if (!actionsLoaded)` 
   - Since flag might be true (from previous successful load in session), it skips the API call
   - Just calls `renderActions()` with empty data
   - Result: No actions shown!

## The Fix

### 1. Improved Error Handling in Pre-load
```javascript
fetch('/api/actions').then(r => r.json()).then(data => {
    if (data.status === 'success') {
        actionsData = data.actions;
        actionsLoaded = true;
        const badge = document.getElementById('actionsBadge');
        badge.textContent = data.actions.length;
    }
}).catch(err => {
    console.error('[photo_viewer] Failed to pre-load actions:', err);
    actionsLoaded = false;  // ✅ Reset flag on error
});
```

### 2. Better Error Messages in loadActions()
```javascript
function loadActions() {
    fetch('/api/actions').then(r => r.json()).then(data => {
        if (data.status === 'success') {
            actionsData = data.actions;
            actionsLoaded = true;
            renderActions();
            const badge = document.getElementById('actionsBadge');
            badge.textContent = actionsData.length;
        } else {
            throw new Error(data.error || 'Unknown error');  // ✅ Propagate error
        }
    }).catch(err => {
        console.error('[photo_viewer] Failed to load actions:', err);
        actionsLoaded = false;  // ✅ Reset flag
        document.getElementById('actionsList').innerHTML =
            `<div class="empty-state">Failed to load actions: ${err.message}</div>`;
    });
}
```

### 3. Defensive Programming in renderActions()
```javascript
function renderActions() {
    if (!actionsData || !Array.isArray(actionsData)) {
        document.getElementById('actionsList').innerHTML =
            '<div class="empty-state">No actions data available</div>';
        return;
    }
    // ... rest of render logic
}
```

### 4. Added Logging to Optional Data Fetches
Even for non-critical data (planogram facings, sales data), we now log errors:

```javascript
Promise.all([
    fetch('/api/planogram-facings').then(r => r.json()).catch(err => {
        console.error('[photo_viewer] Failed to load planogram facings:', err);
        return {};
    }),
    fetch('/api/sales-data').then(r => r.json()).catch(err => {
        console.error('[photo_viewer] Failed to load sales data:', err);
        return {};
    }),
])
```

### 5. Fixed Photo List Loading Error Handling
```javascript
fetch('/api/photo-list?source=supabase')
    .then(r => r.json())
    .then(data => { /* ... */ })
    .catch(err => {
        console.error('[photo_viewer] Failed to load photos from Supabase:', err);
        reloadCurrentView();
    });
```

## Key Learnings

### 1. Never Silently Catch Errors
```javascript
// ❌ BAD
.catch(() => {})

// ✅ GOOD
.catch(err => {
    console.error('[context] Error:', err);
    // Reset state / show user-friendly message
})
```

### 2. Always Reset State on Error
When using flags like `isLoaded`, `isFetching`, etc., **always reset them on error**:

```javascript
try {
    data = await fetchData();
    isLoaded = true;
} catch (err) {
    isLoaded = false;  // ✅ Critical!
    console.error(err);
}
```

### 3. Validate Data Before Using
```javascript
if (!data || !Array.isArray(data)) {
    // Handle invalid state
    return;
}
```

### 4. Provide Clear Error Messages to Users
Instead of silently failing, show what went wrong:
- Network error? "Connection failed"
- API error? Show the error message
- No data? "No actions available"

## Testing the Fix

After deploying, verify:
1. ✅ Actions load correctly on first page load
2. ✅ If API fails, error message is shown (not blank screen)
3. ✅ Console shows error details for debugging
4. ✅ Subsequent clicks on Actions button retry the API call
5. ✅ Badge count matches actual actions loaded

## Prevention

Add this pattern to all async data loading:
```javascript
let dataLoaded = false;
let data = [];

async function loadData() {
    try {
        const response = await fetch('/api/endpoint');
        const result = await response.json();
        
        if (result.status === 'success') {
            data = result.data;
            dataLoaded = true;
            render();
        } else {
            throw new Error(result.error || 'Unknown error');
        }
    } catch (err) {
        console.error('[Component] Load failed:', err);
        dataLoaded = false;  // Reset state
        showError(err.message);
    }
}
```

## Related Files
- `templates/photo_viewer.html` - Fixed error handling in actions loading
- `app.py` - `/api/actions` endpoint (no changes needed)
- `scripts/create_out_of_shelf_actions.py` - Script to populate actions table

## Date
2026-03-06
