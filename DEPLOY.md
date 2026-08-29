# Deploy

The dashboard (`web/`) is a fully static, self-contained site — no server,
no build step, no fetch(). Everything it needs is inside `web/`: `index.html`,
`app.js`, `style.css`, and `data/runs.js` (the curated 13-run evidence trail,
inlined as a JS literal specifically to dodge `file://` CORS — see
`web/data/build_runs_json.py`). The only external reference is Google Fonts.
Confirmed by deploying `web/` alone with nothing else in the repo present.

## Live path: Cloudflare Pages

Deployed via `wrangler`, not git integration — this repo does not need to be
connected to Cloudflare for pushes to redeploy it, and pushing to `master`
does **not** currently trigger a redeploy.

- **Cloudflare account:** josephmpeluso@gmail.com
- **Pages project:** `agentdesk`
- **Production branch (project setting):** `master` — matches this repo's
  actual default branch, and matches the convention already used by the
  other Pages project on this account.
- **Default `.pages.dev` URL:** https://agentdesk-4f6.pages.dev — Cloudflare
  appended `-4f6` because the bare `agentdesk` subdomain was already taken
  elsewhere on Cloudflare's shared `.pages.dev` namespace.
- **Target custom domain:** `agentdesk.joeypeluso.com` (not yet attached —
  see below)

### Redeploying

```bash
npx.cmd wrangler pages deploy web --project-name agentdesk --branch master
```

Run this from the repo root after any change under `web/`. `npx.cmd`, not
plain `npx` — plain `npx` invokes `npx.ps1` in PowerShell on this machine,
which the execution policy here blocks.

### Attaching `agentdesk.joeypeluso.com`

`joeypeluso.com` is already on this Cloudflare account via Cloudflare
Registrar, so this is a same-account custom domain, not a cross-account
handoff:

1. Cloudflare dashboard → **Workers & Pages** → **agentdesk** project →
   **Custom domains** tab → **Set up a custom domain**.
2. Enter `agentdesk.joeypeluso.com` and confirm.
3. Because `joeypeluso.com`'s zone is already on this account, Cloudflare
   creates the required DNS record (a CNAME to the Pages project)
   automatically — no manual DNS editing, no leaving the Pages UI.
4. SSL provisioning is automatic and usually finishes within a few minutes.
   The custom domain becomes the canonical URL; the `.pages.dev` URL keeps
   working alongside it.

## Not the live path: GitHub Pages

`.github/workflows/pages.yml` still exists in this repo but is **not** the
live deploy path. It was built first, before the decision to use Cloudflare
Pages instead — the deciding factors were keeping this project in the same
Cloudflare account as the existing `joeypeluso.com` portfolio Pages project,
and avoiding the requirement GitHub Pages has on the Free plan that the
source repo be public. This repo stays private under Cloudflare Pages.

The workflow file is left in place rather than deleted in case the decision
ever reverses — it's inert (`workflow_dispatch`-only, and Pages was never
enabled in this repo's GitHub settings), so it costs nothing to keep.
