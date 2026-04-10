# Intellexa

## Frontend Deployment (Vercel)

The repository is configured for frontend deployment directly from the repo root.

### What is already configured

- `vercel.json` builds the Vite app from `client/`
- SPA fallback is enabled so routes like `/sign-in`, `/sign-up`, and `/dashboard` work on refresh
- `.vercelignore` excludes backend and unnecessary files from deployment upload

### Required Vercel Environment Variable

Set this in Vercel Project Settings > Environment Variables:

- `VITE_CLERK_PUBLISHABLE_KEY`

Use `client/.env.example` as reference.

### Clerk Redirect URLs

In Clerk, add your Vercel domain URLs (replace with your real domain):

- `https://your-project.vercel.app/`
- `https://your-project.vercel.app/sign-in`
- `https://your-project.vercel.app/sign-up`
- `https://your-project.vercel.app/dashboard`

Also set post-login redirects to `/dashboard`.