# Deployment Guide

## Live URLs

- **Production**: https://plano-agent.vercel.app
- **Photo Viewer**: https://plano-agent.vercel.app/photo-viewer

## Deployment Status

✅ Successfully deployed to Vercel

## Quick Deploy

To deploy updates:

```bash
npx vercel --prod
```

To force a fresh deployment (clears cache):

```bash
npx vercel --prod --force
```

## Environment Variables

The following environment variables are configured in Vercel:

- `GEMINI_API_KEY` - Google Gemini API key for AI-powered planogram generation
- `SUPABASE_URL` - Supabase project URL (has default fallback in code)
- `SUPABASE_KEY` - Supabase API key (has default fallback in code)

### Managing Environment Variables

Add a new environment variable:
```bash
npx vercel env add VARIABLE_NAME production --value "value" --yes
```

List environment variables:
```bash
npx vercel env ls
```

Remove an environment variable:
```bash
npx vercel env rm VARIABLE_NAME production
```

## Vercel Configuration

The deployment is configured via `vercel.json`:

- **Build**: Uses `@vercel/python` builder
- **Runtime**: Python 3.12
- **Entry Point**: `api/index.py`
- **Static Assets**: Served from `/static` directory
- **Demo Images**: Served from `/Demo data` directory (via `/demo-images` route)
- **Max Lambda Size**: 50MB

## Project Structure

```
.
├── api/
│   └── index.py          # Vercel entry point
├── app.py                # Flask application
├── templates/            # HTML templates
├── static/              # CSS, JS, images
├── Demo data/           # Demo photos and data
├── data/                # Product catalogs, planograms
├── requirements.txt     # Python dependencies
└── vercel.json          # Vercel configuration
```

## Dependencies

All dependencies are listed in `requirements.txt`:

- `flask>=3.0` - Web framework
- `google-genai>=1.0` - Gemini AI integration
- `python-dotenv>=1.0` - Environment variable management
- `requests>=2.31.0` - HTTP client for Supabase API

## Deployment Logs

View deployment logs:
```bash
npx vercel inspect plano-agent.vercel.app --logs
```

## Troubleshooting

### Build Failures

1. Check build logs in Vercel dashboard
2. Verify all dependencies are in `requirements.txt`
3. Ensure Python version compatibility (currently 3.12)

### Runtime Errors

1. Check function logs: `npx vercel inspect <deployment-url> --logs`
2. Verify environment variables are set correctly
3. Check that all required files are included (not in `.vercelignore`)

### Static Files Not Loading

1. Verify files are in `/static` directory
2. Check `vercel.json` routes configuration
3. Ensure files aren't excluded in `.vercelignore`

## Local Development

Run locally to test before deploying:

```bash
python app.py
```

Access at http://localhost:5001

## CI/CD Integration

The project is connected to GitHub. To enable automatic deployments:

1. Push code to GitHub
2. Vercel will automatically detect changes
3. Deployments happen on every push to `main` branch

## Performance Optimization

- Lambda function size: 50MB max
- Python packages cached between builds
- Static assets served via Vercel Edge Network
- Images excluded from deployment (`.vercelignore`)

## Security

- Environment variables stored securely in Vercel
- API keys not committed to repository
- `.env` file in `.gitignore`
- Supabase credentials have read-only fallbacks

## Monitoring

Monitor your deployment at:
- https://vercel.com/paulalexeevichs-projects/plano-agent

Available metrics:
- Function invocations
- Error rate
- Response time
- Bandwidth usage

## Cost Considerations

Vercel Hobby Plan includes:
- 100 GB bandwidth/month
- 100 GB-hours serverless function execution
- Unlimited deployments
- Free SSL certificates

Upgrade to Pro if you need:
- More bandwidth
- Higher function limits
- Team collaboration
- Advanced analytics

## Support

For Vercel-specific issues:
- Documentation: https://vercel.com/docs
- Support: https://vercel.com/support
