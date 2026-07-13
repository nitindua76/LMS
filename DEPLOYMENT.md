# Production Deployment

Internal-network deployment on a Windows VM via Docker, with GitHub Actions
building and deploying automatically on every push to `main`. Everything
after the one-time setup below is automatic — this doc is only the part
that needs a human with access to the VM and the GitHub repo.

## Architecture

- **CI** (`.github/workflows/deploy.yml`, GitHub-hosted runner): builds the
  `api` and `web` Docker images and pushes them to GHCR
  (`ghcr.io/<org>/<repo>-api`, `...-web`).
- **CD** (same workflow, **self-hosted runner on the production VM**):
  pulls those images and restarts the stack via `scripts/deploy.ps1`.
  A self-hosted runner is what makes this work for a VM with no public
  IP/inbound access — the runner polls GitHub outbound, so nothing needs to
  connect in.
- **Caddy** terminates TLS in front of the app (self-signed "internal" cert
  — there's no public DNS to get a real Let's Encrypt one) and in front of
  LiveKit's signaling port. Media (audio/video) is UDP and bypasses Caddy
  entirely — LiveKit publishes those ports directly.

## One-time setup (do this once, in order)

### 1. Check out the repo on the VM

Pick a fixed path, e.g. `C:\lms`, and `git clone` the repo there. This same
checkout is what the self-hosted runner will operate on and what
`scripts\deploy.ps1` runs from.

### 2. Point a hostname at the VM

Add an internal DNS record (or, for a quick start, a `hosts` file entry on
each employee's machine) mapping something like `lms.internal` to this VM's
LAN IP. You'll use that hostname as `INTERNAL_HOSTNAME` below.

### 3. Bootstrap the VM

As Administrator, from the repo root:

```powershell
powershell -File scripts\setup-prod-vm.ps1
```

First run creates `.env.prod` from the template and stops so you can fill
it in. Open `.env.prod` and set real values — at minimum:
`INTERNAL_HOSTNAME`, `LIVEKIT_NODE_IP` (the VM's actual LAN IP), and every
`change-me` secret (the file has `python -c "..."` one-liners for
generating each one). Then run the same command again — it'll create the
firewall rules and run the first deploy.

### 4. Install a self-hosted GitHub Actions runner on this VM

GitHub repo → **Settings → Actions → Runners → New self-hosted runner** →
follow the Windows instructions shown there (download, `config.cmd`,
`run.cmd`, or install it as a service with `svc install` so it survives
reboots). Once it shows as **Idle** in that Runners list, every push to
`main` will build and deploy automatically.

### 5. Distribute Caddy's internal root CA (removes the browser warning)

Because there's no public domain, Caddy acts as its own certificate
authority. Employees will see a "not trusted" warning until that root CA is
installed on their machines:

```powershell
docker compose -f docker-compose.prod.yml cp caddy:/data/caddy/pki/authorities/local/root.crt .\lms-root-ca.crt
```

Distribute `lms-root-ca.crt` via Group Policy (Computer Configuration →
Windows Settings → Security Settings → Public Key Policies → Trusted Root
Certification Authorities) or have people install it manually
(double-click → Install Certificate → Local Machine → Trusted Root
Certification Authorities). Until this is done, people can still use the
app by clicking through the browser warning, but camera/mic in live
sessions require the connection to actually be trusted as secure — get
this distributed before relying on video sessions org-wide.

## Everyday use

Just `git push` to `main`. CI builds, pushes to GHCR, and the runner on the
VM deploys automatically — new images, migrations, and old-image cleanup
all handled by `scripts/deploy.ps1`.

To deploy manually (skip CI, e.g. to test a fix directly on the VM):

```powershell
powershell -File scripts\deploy.ps1
```

To trigger a CI deploy without a new commit (redeploy the current `main` as-is):
GitHub repo → **Actions** → *Build and Deploy* → **Run workflow**.

## Known gaps / things to revisit later

- **Secrets already in git**: `.env` (dev secrets) is currently tracked in
  the repo's git history. A `.gitignore` now exists to stop that going
  forward, but the already-committed values should be treated as
  compromised — rotate `JWT_SECRET` and anything else in that file, and
  consider whether the history needs scrubbing (separate, more invasive
  operation — ask before doing that).
- **TURN is disabled** in the production LiveKit config — fine for
  same-network/VPN users; if remote users report video sessions failing to
  connect, TURN needs its own TLS cert (Caddy's internal CA isn't directly
  reusable for TURN's own TLS termination) — a follow-up task, not a
  blocker for initial rollout.
- **No automated backups** configured for the `postgres_data` /
  `minio_data` Docker volumes — worth adding before this holds real
  long-term data.
