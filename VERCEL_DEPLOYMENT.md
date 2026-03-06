# Vercel Deployment Guide

## 🎉 Deployment Successful!

Your Planogram Agent application has been successfully deployed to Vercel.

### 🌐 Live URLs

- **Production URL**: https://plano-agent.vercel.app
- **Current Deployment**: https://plano-agent-di49rzbmg-paulalexeevichs-projects.vercel.app
- **Deployment Dashboard**: https://vercel.com/paulalexeevichs-projects/plano-agent

---

## 📋 Deployment Details

- **Build Time**: ~24 seconds
- **Python Version**: 3.12 (auto-detected)
- **Region**: Washington, D.C., USA (iad1)
- **Status**: ✅ Deployed and Live

---

## 🔧 Configuration Files

### 1. `vercel.json`
```json
{
  "version": 2,
  "builds": [
    {
      "src": "api/index.py",
      "use": "@vercel/python",
      "config": {
        "includeFiles": "{Demo data/**,templates/**,data/**,static/**}"
      }
    }
  ],
  "routes": [
    {
      "src": "/static/(.*)",
      "dest": "/static/$1"
    },
    {
      "src": "/(.*)",
      "dest": "/api/index.py"
    }
  ]
}
```

### 2. `.vercelignore`
Excludes unnecessary files:
- Python cache files (`__pycache__`, `*.pyc`)
- Environment files (`.env`, `.env.local`)
- Image files (`*.png`, `*.jpg`)
- Development directories (`venv`, `.cursor`)

---

## ⚙️ Environment Variables

**IMPORTANT**: Set up environment variables in Vercel dashboard:

1. Go to: https://vercel.com/paulalexeevichs-projects/plano-agent/settings/environment-variables
2. Add the following variables:

| Variable Name | Value | Environment |
|---------------|-------|-------------|
| `GEMINI_API_KEY` | Your Gemini API key | Production, Preview, Development |
| `SUPABASE_URL` | https://zcciroutarcpkwpnynyh.supabase.co | Production, Preview, Development |
| `SUPABASE_KEY` | Your Supabase anon key | Production, Preview, Development |

**Note**: Never commit `.env` files to Git. Environment variables should be set in Vercel dashboard.

---

## 🚀 Redeployment

To redeploy after making changes:

```bash
# Deploy to production
npx vercel --prod

# Deploy to preview (for testing)
npx vercel
```

Or use Git integration:
- Push to `main` branch → auto-deploys to production
- Push to other branches → creates preview deployments

---

## 📊 Monitoring & Logs

### View Logs
```bash
# View deployment logs
npx vercel inspect plano-agent-di49rzbmg-paulalexeevichs-projects.vercel.app --logs

# View function logs (runtime errors)
npx vercel logs plano-agent.vercel.app
```

### Deployment Dashboard
Visit: https://vercel.com/paulalexeevichs-projects/plano-agent

Here you can:
- View deployment history
- Check build logs
- Monitor function errors
- Manage environment variables
- View analytics

---

## 🔍 Testing the Deployment

1. Visit https://plano-agent.vercel.app
2. Test key features:
   - Load Coffee mode: https://plano-agent.vercel.app/?mode=coffee
   - Load Beer mode: https://plano-agent.vercel.app/?mode=beer
   - Photo Viewer: https://plano-agent.vercel.app/photo-viewer
   - Settings (⚙ icon): Verify Supabase is default data source

---

## ⚠️ Common Issues & Solutions

### Issue: 500 Internal Server Error
**Solution**: Check environment variables are set correctly in Vercel dashboard.

### Issue: Static files not loading (CSS/JS)
**Solution**: Verify `vercel.json` includes static files in routes.

### Issue: "Module not found" errors
**Solution**: Ensure all dependencies are in `requirements.txt`.

### Issue: Timeout errors
**Solution**: Vercel serverless functions have a 10-second timeout (Pro: 60s). Optimize long-running operations.

---

## 📝 File Structure

```
.
├── api/
│   └── index.py           # Vercel serverless entry point
├── static/                # Frontend assets (CSS, JS)
├── templates/             # Jinja2 HTML templates
├── data/                  # JSON data files
├── Demo data/             # Demo images and data
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── vercel.json           # Vercel configuration
└── .vercelignore         # Files to exclude from deployment
```

---

## 🔄 Automatic Deployments

Enable Git integration for automatic deployments:

1. Go to: https://vercel.com/paulalexeevichs-projects/plano-agent/settings/git
2. Connect your GitHub repository
3. Configure:
   - Production branch: `main`
   - Auto-deploy: ✅ Enabled

Now every push to `main` will auto-deploy to production!

---

## 📈 Next Steps

1. ✅ **Set Environment Variables** in Vercel dashboard
2. ✅ **Test the deployment** at https://plano-agent.vercel.app
3. ✅ **Enable Git integration** for automatic deployments
4. ✅ **Monitor logs** for any runtime errors
5. ✅ **Set up custom domain** (optional) in Vercel dashboard

---

## 🛠 Development Workflow

```bash
# Local development
python3 app.py

# Test with Vercel dev (simulates production environment)
npx vercel dev

# Deploy to preview (testing)
npx vercel

# Deploy to production
npx vercel --prod
```

---

## 📞 Support

- **Vercel Documentation**: https://vercel.com/docs
- **Vercel Support**: https://vercel.com/support
- **Project Dashboard**: https://vercel.com/paulalexeevichs-projects/plano-agent

---

**Deployment Date**: March 6, 2026  
**Deployed by**: Cursor AI Assistant  
**Status**: ✅ Live and Production-Ready
