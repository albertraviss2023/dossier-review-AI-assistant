# Public Demo Deployment (Gemini Provider)

This project supports a public demo profile without forking feature logic.

## Runtime switch

Use environment variables only:

- `DOSSIER_MODEL_PROVIDER=gemini`
- `DOSSIER_LOCAL_MODEL_ENABLED=false`
- `DOSSIER_GEMINI_ENABLED=true`
- `DOSSIER_GEMINI_API_KEY_ENV=GEMINI_API_KEY`
- `DOSSIER_GEMINI_MODEL=gemini-2.5-pro`
- `DOSSIER_DEMO_MODE=true`

Local development keeps:

- `DOSSIER_MODEL_PROVIDER=local`
- `DOSSIER_LOCAL_MODEL_ENABLED=true`
- `DOSSIER_GEMINI_ENABLED=false`

## Hugging Face Space (Docker)

1. Ensure the Space is created as a Docker Space.
2. Set Space secret `GEMINI_API_KEY`.
3. Configure CORS for your public frontend domain:

```env
DOSSIER_CORS_ORIGINS=https://your-vercel-app.vercel.app,https://your-hf-space-url.hf.space
```
3. Deploy this repository content (or enable GitHub Action sync).
4. Space starts with:

```bash
uvicorn dossier_review_ai_assistant.api:app --host 0.0.0.0 --port ${PORT:-7860}
```

## Auto-deploy from main

Workflow file:

- `.github/workflows/deploy_hf_demo.yml`

Required GitHub config:

- Secret: `HF_TOKEN`
- Variable: `HF_SPACE_REPO` (format: `org-or-user/space-name`)

Each push to `main` syncs demo files to the Space so public demo tracks local feature updates.

## Vercel usage

Recommended use for Vercel:

- Host the same UI and call backend API on HF Space using `api_base`.

Example:

- `https://your-vercel-app.vercel.app/review?api_base=https://your-hf-space-url.hf.space`
- `https://your-vercel-app.vercel.app/admin?api_base=https://your-hf-space-url.hf.space`

The `api_base` value is persisted in browser local storage for subsequent requests.
