# Vercel Deployment Checklist - Actions Loading Issue

## Problem on Vercel Production
Actions panel shows "Loading actions..." indefinitely and never loads data.

## Root Causes

### 1. Supabase Query Timeout
- **Issue**: No limit on query fetching ALL actions
- **Impact**: Slow query on cold start, can exceed Vercel's 10s timeout
- **Fix**: Added `limit` parameter (default 100, max 500)

### 2. Missing Environment Variables
- **Issue**: SUPABASE_URL and SUPABASE_KEY might not be set in Vercel
- **Impact**: Silent failure with no useful error message
- **Fix**: Added explicit check and helpful error message

### 3. No Client-Side Timeout
- **Issue**: Fetch could hang indefinitely with no user feedback
- **Impact**: "Loading..." shown forever with no retry option
- **Fix**: Added 15s timeout with AbortController + retry button

### 4. Poor User Feedback
- **Issue**: Generic error messages don't help debugging
- **Impact**: User can't tell if it's a timeout, missing config, or network issue
- **Fix**: Specific error messages + visual feedback + retry button

## Changes Made

### Backend (`app.py`)

#### 1. Added Query Limit
```python
@app.route("/api/actions")
def list_actions():
    try:
        limit = request.args.get("limit", 100, type=int)
        rows = _supabase_get("planogram_actions", {
            "select": "*",
            "order": "avg_sale_amount.desc.nullslast",
            "limit": str(min(limit, 500)),  # Cap at 500
        })
        return jsonify({"status": "success", "actions": rows})
```

#### 2. Check Environment Variables
```python
if not SUPABASE_URL or not SUPABASE_KEY:
    return jsonify({
        "status": "error",
        "error": "Supabase not configured. Set SUPABASE_URL and SUPABASE_KEY."
    }), 503
```

#### 3. Better Error Logging
```python
except Exception as e:
    print(f"[actions] Error: {e}", flush=True)
    traceback.print_exc()
    return jsonify({"status": "error", "error": str(e)}), 500
```

#### 4. Reduced Timeout
```python
def _supabase_get(table: str, params: dict | None = None) -> list:
    resp = http_requests.get(url, headers=_SUPABASE_HEADERS, params=params, timeout=5)
```

### Frontend (`photo_viewer.html`)

#### 1. Client-Side Timeout with AbortController
```javascript
const controller = new AbortController();
const fetchTimeout = setTimeout(() => controller.abort(), 15000);

fetch('/api/actions', { signal: controller.signal })
    .then(r => {
        clearTimeout(fetchTimeout);
        // ...
    })
    .catch(err => {
        const errMsg = err.name === 'AbortError' 
            ? 'Request timed out (>15s). Server might be slow or unavailable.'
            : err.message;
        // Show error with retry button
    });
```

#### 2. Progressive Feedback
- 0-8s: "Loading actions..."
- 8s+: "⏱️ Loading is taking longer than expected..." + Retry button
- 15s+: "❌ Failed to load" + specific error + Retry button

#### 3. Retry Button
Always show a retry button on errors so users can try again without refreshing.

## Vercel Environment Variables to Set

Go to Vercel Project → Settings → Environment Variables and add:

```bash
SUPABASE_URL=https://zcciroutarcpkwpnynyh.supabase.co
SUPABASE_KEY=eyJhbGci...  # Your Supabase anon key
```

**Important**: 
- Set for Production, Preview, and Development
- Redeploy after adding environment variables

## Testing Checklist

### Local Testing
- [x] Test with `flask run` locally
- [x] Verify actions load correctly
- [x] Test error handling by temporarily breaking Supabase URL
- [x] Check console logs show helpful messages

### Vercel Testing
- [ ] Verify environment variables are set in Vercel dashboard
- [ ] Deploy to Vercel
- [ ] Test actions loading on production URL
- [ ] Check Vercel logs for any errors: `vercel logs [deployment-url]`
- [ ] Test with network throttling to verify timeout handling
- [ ] Verify retry button works

## Debugging Tips

### If actions still don't load:

1. **Check Vercel Logs**
```bash
vercel logs --follow
```

2. **Check Browser Console**
- Open DevTools → Console
- Look for `[photo_viewer]` messages
- Check Network tab for `/api/actions` request

3. **Test API Directly**
```bash
curl https://your-vercel-url.vercel.app/api/actions
```

4. **Common Issues**
- Missing env vars → Shows "Supabase not configured"
- Timeout → Shows "Request timed out (>15s)"
- CORS → Check if request is cross-origin
- Cold start → First request might be slow (8-10s)

## Performance Notes

### Vercel Serverless Limits
- **Hobby tier**: 10s execution timeout
- **Cold start**: 2-5s on first request
- **Warm cache**: <1s on subsequent requests

### Optimization
- Limited query to 100 actions by default (user can request more)
- Reduced Supabase timeout from 10s → 5s
- Client-side timeout at 15s (gives server time to respond)

## Rollback Plan

If this causes issues, revert with:
```bash
git revert HEAD
git push
```

## Related Files
- `app.py` - Backend API optimizations
- `templates/photo_viewer.html` - Frontend timeout handling
- `.cursor/rules/actions-disappearing-fix.md` - Original error handling fix

## Date
2026-03-06
