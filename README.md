# LMS — Developer Setup

## One-time: dev hostnames

The LMS uses **two genuinely different registrable domains** in development so that
browser cookie-scoping (SameSite) enforces isolation between the main app and the
SCORM/cmi5 content origin, exactly as it does in production.

| Origin | Registrable domain (eTLD+1) | Purpose |
|---|---|---|
| `http://lms.local:5173` | `lms.local` | React app (Vite dev server) |
| `http://lms.local:8000` | `lms.local` | FastAPI (also accessible via Vite proxy at `/api`) |
| `http://content.local:5174` | `content.local` | SCORM/cmi5 package delivery (nginx) |

Because `lms.local` ≠ `content.local` (different eTLD+1), the session cookie at
`lms.local` is **never sent or readable** from `content.local` — not for simple
requests, not for preflighted requests, not by JavaScript running in a SCORM package.

> **Why not `localtest.me`?** `lms.localtest.me` and `content.localtest.me` share the
> same eTLD+1 (`localtest.me`) and are same-site. SameSite=Lax would not prevent
> cross-subdomain cookie access. Port differences on `localhost` have the same problem.

### Add hosts entries (run once, requires admin/sudo)

**macOS / Linux:**
```bash
echo "127.0.0.1 lms.local" | sudo tee -a /etc/hosts
echo "127.0.0.1 content.local" | sudo tee -a /etc/hosts
```

**Windows (PowerShell as Administrator):**
```powershell
Add-Content -Path C:\Windows\System32\drivers\etc\hosts -Value "127.0.0.1 lms.local"
Add-Content -Path C:\Windows\System32\drivers\etc\hosts -Value "127.0.0.1 content.local"
```

Both names resolve to `127.0.0.1`. No DNS required; it's the same loopback as
`localhost` — only the hostname that the browser sees changes.

## Start the stack

```bash
docker compose up --build
```

Then open **http://lms.local:5173** in your browser.

> The Vite dev-server proxy forwards `/api/*` → `http://localhost:8000` (Node.js side,
> never the browser). Direct SCORM runtime XHR calls go from `content.local:5174`
> straight to `lms.local:8000`.

## Security model (cross-origin isolation)

```
Browser
├── lms.local:5173  (React app)
│   └── cookies: access_token, refresh_token, csrf_token  ← scoped to lms.local
│
└── content.local:5174  (SCORM/cmi5 iframe)
    ├── document.cookie → ""   (different site; lms.local cookies not visible)
    └── XHR → lms.local:8000/api/scorm/*
            ← Content-Type: application/json  (forces CORS preflight)
            ← X-SCORM-Token: <short-lived token>  (no session cookie)
            ← Access-Control-Allow-Credentials absent  (intentional)
```

**Attack surface closed by this setup:**

| Attack | Before (localhost ports) | After (different eTLD+1) |
|---|---|---|
| Simple POST from content origin with session cookie | POSSIBLE — same-site, cookie sent | BLOCKED — cross-site, SameSite=Lax drops cookie |
| `document.cookie` read from package JS | POSSIBLE — same-site | BLOCKED — cookies not visible cross-site |
| Preflighted request with credentials | Blocked by CORS middleware | Also blocked by CORS middleware (defence in depth) |
| SCORM runtime calls (X-SCORM-Token) | Allowed, no session cookie attached | Allowed, no session cookie attached |

## Environment variables

Key variables in `.env`:

| Variable | Example | Notes |
|---|---|---|
| `CORS_ORIGINS` | `http://lms.local:5173` | Only the LMS frontend; never the content origin |
| `CONTENT_ORIGIN` | `http://content.local:5174` | Matched by `scorm_cors_middleware` |
| `API_EXTERNAL_URL` | `http://lms.local:8000` | Embedded in SCORM/cmi5 launch URLs so the browser can reach the API directly (not through the Vite proxy) |
| `VITE_API_URL` | `http://localhost:8000` | Used by the Vite proxy on the Node.js side only |
