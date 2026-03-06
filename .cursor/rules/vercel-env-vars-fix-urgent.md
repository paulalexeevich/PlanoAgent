# URGENT: Fix Vercel Environment Variables

## Current Issue

The Vercel deployment is failing with this error:
```
Failed to resolve 'zcciroutarcpkwpnynyh.supabase.co%0a'
```

The `%0a` is a **newline character** - this means the environment variable in Vercel contains trailing whitespace.

## Root Cause

When setting environment variables in the Vercel dashboard, if you accidentally added a newline (pressing Enter) after pasting the value, Vercel stores that newline as part of the variable value.

## How to Fix

### Option 1: Fix Environment Variables in Vercel Dashboard (RECOMMENDED)

1. **Go to Vercel Dashboard**: https://vercel.com/
2. **Select your project**: PlanoAgent (or plano-agent)
3. **Go to Settings → Environment Variables**
4. **Delete the existing variables**:
   - Delete `SUPABASE_URL`
   - Delete `SUPABASE_KEY`

5. **Re-add them carefully** (without trailing newlines):

   **SUPABASE_URL:**
   ```
   https://zcciroutarcpkwpnynyh.supabase.co
   ```
   ⚠️ **DO NOT press Enter after pasting!** Just click "Save"

   **SUPABASE_KEY:**
   ```
   eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpjY2lyb3V0YXJjcGt3cG55bnloIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI3MjIzMTAsImV4cCI6MjA4ODI5ODMxMH0.LFnJ8WoxlNhZ06MBQm-1mmJK4mtkBLZAPd4UoPtGrkE
   ```
   ⚠️ **DO NOT press Enter after pasting!** Just click "Save"

6. **Important**: Set for **all environments**:
   - ☑️ Production
   - ☑️ Preview  
   - ☑️ Development

7. **Redeploy**: After saving, trigger a new deployment:
   - Go to Deployments tab
   - Click "..." menu on the latest deployment
   - Click "Redeploy"

### Option 2: Use Vercel CLI

If you have Vercel CLI installed:

```bash
vercel env rm SUPABASE_URL production
vercel env rm SUPABASE_KEY production
vercel env add SUPABASE_URL production
# Paste: https://zcciroutarcpkwpnynyh.supabase.co
vercel env add SUPABASE_KEY production
# Paste: eyJhbGci... (the full key)

# Then redeploy
vercel --prod
```

## Code Fix Already Applied

The code now strips whitespace automatically (commit `2c7d593`):

```python
SUPABASE_URL = os.environ.get("SUPABASE_URL", "...").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "...").strip()
```

This will help prevent future issues, **but you still need to fix the env vars in Vercel** because:
- Vercel caches the environment variables
- The `.strip()` might not be applied if the deployment is using old code

## How to Verify It's Fixed

After updating the environment variables and redeploying:

```bash
# Test the API endpoint
curl https://plano-agent.vercel.app/api/actions

# Should return JSON with actions, not an error
# Example of success:
# {"status":"success","actions":[{"id":124,"product_name":"...","avg_sale_amount":3136.69,...}]}
```

## Testing Checklist

- [ ] Environment variables updated in Vercel (no trailing newlines)
- [ ] Variables set for all environments (Production, Preview, Development)
- [ ] Redeployed after updating env vars
- [ ] API endpoint returns success: `curl https://plano-agent.vercel.app/api/actions`
- [ ] Photo Viewer loads actions correctly when clicking Actions button
- [ ] Browser console shows no errors

## Common Mistakes to Avoid

❌ **DON'T**: Press Enter after pasting values in Vercel dashboard
❌ **DON'T**: Add quotes around the values (unless they're part of the value)
❌ **DON'T**: Copy from terminal output that includes newlines
✅ **DO**: Copy directly from source, paste, and immediately save
✅ **DO**: Verify in Vercel UI that there's no extra space after the value
✅ **DO**: Redeploy after changing env vars

## If Still Not Working

1. **Check Vercel Logs**:
   ```bash
   # If you have Vercel CLI:
   vercel logs --follow
   
   # Or in browser:
   # Go to Deployments → Click on deployment → Click "View Function Logs"
   ```

2. **Check the exact error**:
   - Look for `%0a`, `%0d`, or `%20` in error messages (these indicate whitespace)
   - URL should be exactly: `https://zcciroutarcpkwpnynyh.supabase.co`
   - NOT: `https://zcciroutarcpkwpnynyh.supabase.co%0a`

3. **Force fresh deployment**:
   - In Vercel, go to Settings → Advanced
   - Scroll to "Clear Build Cache"
   - Click it, then redeploy

## Date
2026-03-06

## Status
- [x] Bug identified (trailing newline in env vars)
- [x] Code fix deployed (`.strip()` added)
- [x] **FIXED**: Environment variables corrected via Vercel CLI
- [x] **VERIFIED**: API returns 21 actions successfully (10 high, 5 medium, 6 low priority)
- [x] Production deployment working: https://plano-agent.vercel.app/api/actions

## Resolution Summary

**Fixed via Vercel CLI on 2026-03-06:**

```bash
# Removed old variables with trailing newlines
npx vercel env rm SUPABASE_URL production --yes
npx vercel env rm SUPABASE_KEY production --yes

# Added clean variables (using echo -n to prevent newlines)
echo -n "https://zcciroutarcpkwpnynyh.supabase.co" | npx vercel env add SUPABASE_URL production
echo -n "eyJhbGci..." | npx vercel env add SUPABASE_KEY production

# Deployed to production
npx vercel --prod --yes
```

**Result**: API now returns `{"status":"success","actions":[...]}` with 21 out-of-shelf products.
