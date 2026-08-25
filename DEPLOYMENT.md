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

## Moving production to a different VM

If the production deployment needs to move to a different physical/virtual
machine (new hardware, different network segment, etc.), the app tier
(api/web images, Caddy config) is stateless and just needs a normal fresh
deploy on the new VM — the only real work is moving the DATA: the Postgres
database and the MinIO object storage (uploaded videos/PDFs/SCORM
packages). Two scripts handle this:

### On the OLD VM (source)

```powershell
powershell -File scripts\export-for-migration.ps1
```

Produces a timestamped folder (`lms-migration-<timestamp>\`) containing a
Postgres dump, a tarball of the MinIO volume, and a manifest — everything
needed to reconstruct the data, nothing else (no secrets, no `.env.prod`,
no TLS keys). Copy that whole folder to the new VM over your internal
network/file share — never over the public internet, it contains real
employee data.

### On the NEW VM (target)

1. Complete DEPLOYMENT.md steps 1-3 above as normal (checkout, hostname,
   `setup-prod-vm.ps1` with a filled-in `.env.prod` for the NEW VM — new
   secrets are fine and recommended, they don't need to match the old
   VM's). This brings up an empty stack with a fresh schema/bucket.
2. Copy the exported `lms-migration-<timestamp>\` folder onto this VM.
3. Run:
   ```powershell
   powershell -File scripts\import-migration.ps1 -ExportPath "C:\path\to\lms-migration-<timestamp>" -Confirm
   ```
   This is destructive to whatever's currently in the new VM's database/
   object storage (expected — it's meant to replace the empty just-bootstrapped
   state), which is why `-Confirm` is required. It stops api/web, restores
   Postgres, restores MinIO, restarts everything, and runs migrations.
4. Continue with steps 4-5 above (self-hosted runner, root CA distribution)
   on the new VM if not already done.
5. Point `INTERNAL_HOSTNAME`'s DNS record (or everyone's hosts file entries)
   at the new VM's IP, and decommission the old VM once verified.

Both scripts were verified end-to-end against real isolated Docker Compose
projects (separate project names/volumes, never touching a live
deployment) before being relied on here: seeded a real Postgres row and a
real MinIO object, exported, imported into a second isolated stack, and
confirmed both came through correctly.

## Running dev and prod concurrently on one machine

If this same machine is used for both development (`docker-compose.yml`)
and production (`docker-compose.prod.yml`) — a single-VM setup, no
separate prod hardware — both stacks can run side by side without
interfering, as long as this file's defaults are used as-is. This was
verified end-to-end on this exact host: brought up real containers from
both compose files simultaneously, confirmed zero port/volume/container
name collisions, and confirmed traffic actually routes correctly through
Caddy end-to-end (not just that ports happen to be open).

### Why the prod ports don't look like LiveKit's/Caddy's usual defaults

Two independent problems, both real and specific to running both stacks on
one machine (or in this case, specific to this Windows host at all):

1. **Port collision with dev.** `docker-compose.yml` (dev) already
   publishes `7880` (LiveKit signaling, via the dev nginx TLS proxy),
   `7881` (LiveKit RTC TCP fallback), `55000-55100/udp` (LiveKit RTC media),
   and `5175` (SCORM content origin) directly on the host. If prod used
   those same numbers, whichever stack started second would fail to bind.
2. **This host's own Windows port reservations.** Independent of dev
   entirely: `netsh interface ipv4 show excludedportrange protocol=tcp`
   confirmed port `443` — LiveKit's/Caddy's conventional HTTPS port — falls
   inside a Windows-reserved TCP exclusion range on this machine. Docker
   Desktop cannot bind it here at all, dev or no dev. Port `5174` (prod's
   original hardcoded content-origin port) was found to be in the same
   situation — both excluded AND already occupied by another process. This
   would have been a problem for a prod-only deployment on this exact
   machine too.

If production ever moves to its **own dedicated machine** (see "Moving
production to a different VM" above) with no dev stack and without this
particular Windows host's port reservations, it's safe to override these
back to the more conventional 443/7880/7881/55000-55100/5174 via
`.env.prod` — nothing in the app depends on the specific numbers below,
they're just what avoids collisions on THIS shared machine.

### Full port map

| Purpose                          | Dev (`docker-compose.yml`) | Prod (`docker-compose.prod.yml`, default) |
|-----------------------------------|----------------------------|--------------------------------------------|
| Main app (HTTPS)                  | `5173`                     | `${PROD_HTTPS_PORT}` → **8543**             |
| API (HTTPS, direct)                | `8000`                     | *(no separate port — prod's `web` image proxies `/api/` internally to `api:8000`, see `web/nginx.conf`)* |
| SCORM/cmi5 content origin         | `5175`                     | `${PROD_CONTENT_PORT}` → **8174**           |
| LiveKit signaling (wss://)         | `7880`                     | `${PROD_LIVEKIT_WSS_PORT}` → **8780**       |
| LiveKit RTC (TCP fallback)         | `7881`                     | `${PROD_LIVEKIT_RTC_TCP_PORT}` → **8781**   |
| LiveKit RTC media (UDP range)      | `55000-55100`              | `${LIVEKIT_RTC_PORT_RANGE_START}`–`${LIVEKIT_RTC_PORT_RANGE_END}` → **56000-56100** |
| MinIO (presigned URLs, HTTPS)      | *(not applicable — dev uses `STORAGE_BACKEND=local`)* | `${PROD_MINIO_PUBLIC_PORT}` → **9002** |
| Postgres, Redis, LRS, Mailpit      | published directly (`5437`/`6380`/`9090`/`8025`) for local debugging | not published to the host at all |

Every prod port above is a `.env.prod` variable with the shown default —
override any of them there if a different number is needed (e.g. one of
these also happens to collide with something else already running on a
given machine). `docker-compose.prod.yml` also sets an explicit top-level
`name: lms-prod`, so its containers/volumes/network (`lms-prod-*`,
`lms-prod_*`) never collide with dev's default project name (`lms`,
derived from the folder name) even though both stacks live in the same
repo checkout.

### Verifying this on a new machine

Before relying on this in a real dev+prod-concurrent deployment, confirm
this machine doesn't have its own additional port reservations:

```powershell
netsh interface ipv4 show excludedportrange protocol=tcp
netsh interface ipv4 show excludedportrange protocol=udp
```

If any of the prod defaults above fall inside an excluded range (or are
already bound by something else via `Get-NetTCPConnection -State Listen`),
override that specific `.env.prod` variable to a free, non-excluded port
before running `scripts\setup-prod-vm.ps1` / `scripts\deploy.ps1`.

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
