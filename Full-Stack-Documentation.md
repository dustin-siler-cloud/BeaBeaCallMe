# BeaBeaCallMe — Full Stack Reference

> **Version:** v1.9.3
> **Last Updated:** 2026-06-24
> **Repo:** https://github.com/dustin-siler-cloud/BeaBeaCallMe
> **Purpose:** Self-hosted IVR voicemail so Bea (age 5) can call a Twilio number from her Tin Can kids' phone and leave voicemails that save to Google Drive.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Infrastructure](#infrastructure)
- [Backend Stack](#backend-stack)
- [Notifications](#notifications)
- [CI/CD Pipeline](#cicd-pipeline)
- [Configuration Reference](#configuration-reference)
- [Project Structure](#project-structure)
- [Version History](#version-history)

---

## Architecture Overview

Bea calls a Twilio phone number → Twilio hits `/call` → IVR prompts "press 1 to leave a voicemail" → Bea presses 1 → Twilio records up to 5 minutes → Twilio posts a status callback to `/voicemail/callback` → the app downloads the WAV, saves it locally, uploads it to Google Drive, logs metadata to SQLite, then deletes the recording from Twilio to avoid storage costs.

```
  Bea's Tin Can Phone
         │  PSTN call
         ▼
  ┌─────────────┐
  │   Twilio    │  Managed phone number (~$1.60/mo)
  └──────┬──────┘
         │  HTTPS webhooks (TwiML)
         ▼
  ┌─────────────────────┐
  │  Cloudflare Tunnel  │  Named tunnel — no open inbound ports
  └──────────┬──────────┘
             │  HTTP → localhost:8080
             ▼
  ┌─────────────────────────────────────┐
  │   Windows 11 Gaming PC              │
  │                                     │
  │   Docker → Flask app :8080          │
  │     /call          IVR menu         │
  │     /voicemail     start recording  │
  │     /voicemail/done  hang up        │
  │     /voicemail/callback             │
  │       ├─ download WAV from Twilio   │
  │       ├─ save to ./data/recordings/ │
  │       ├─ upload to Google Drive     │
  │       ├─ log to SQLite              │
  │       ├─ send Slack notification    │
  │       └─ delete from Twilio         │
  └─────────────────────────────────────┘
         │  Google Drive API (service account)
         ▼
  ┌─────────────────┐
  │  Google Drive   │  Shared folder — owner can listen from any device
  └─────────────────┘
```

---

## Infrastructure

### Docker

| Component | Image | Purpose |
|---|---|---|
| **App** | `python:3.13-slim` | Flask IVR app + GDrive uploader |
| **cloudflared** | `cloudflare/cloudflared:2026.6.1` | Cloudflare tunnel connector |

**Compose:**
- `docker-compose.yml` — two services: `app` (port bound to `127.0.0.1:8080`) and `cloudflared` (tunnel connector). `./data` volume for SQLite persistence, `gdrive-credentials.json` mounted read-only from a local path outside the Google Drive virtual filesystem (avoids Docker bind-mount issues with virtual drives).

**Non-root container user:**
The app runs as `appuser` (no password, no shell). An `entrypoint.sh` script runs first as root to `chown /app/data` to `appuser` (the bind-mounted `./data` volume arrives owned by root), then hands off to `gosu appuser gunicorn`.

**Start/rebuild:**
```bash
git checkout main && git pull
docker compose down && docker compose up -d --build
```

### Networking

| Exposure | How |
|---|---|
| Public HTTPS | Cloudflare named tunnel (outbound-only, no open ports) |
| App port | `127.0.0.1:8080` (localhost-only bind) |
| TLS | Terminated by Cloudflare edge |

### Cloudflare Tunnel

A named Cloudflare tunnel runs as a Docker service alongside the app. The `cloudflared` container connects outbound to Cloudflare's edge and routes your public hostname → `http://app:8080` (Docker service name). No open inbound ports required. Token stored in `.env` as `CLOUDFLARE_TUNNEL_TOKEN`.

---

## Backend Stack

### Runtime

| Component | Version | Purpose | Docs |
|---|---|---|---|
| **Python** | 3.13 | Runtime | https://docs.python.org/3.13/ |
| **Flask** | 3.1.3 | Web framework | https://flask.palletsprojects.com/ |
| **Gunicorn** | latest | WSGI server (2 workers, 60s timeout) | https://docs.gunicorn.org/ |
| **python-dotenv** | 1.2.2 | `.env` loading | https://github.com/theskumar/python-dotenv |

### Twilio

| Component | Version | Purpose | Docs |
|---|---|---|---|
| **twilio** | 9.10.9 | Twilio REST client + TwiML builder | https://www.twilio.com/docs/libraries/python |
| **requests** | 2.34.2 | Download recordings from Twilio | https://docs.python-requests.org/ |

**IVR Flow (`app/routes/`):**

| Route | Blueprint | What Happens |
|---|---|---|
| `POST /call` | `ivr` | Entry point — plays main menu ("press 1 to leave a voicemail") |
| `POST /call/route` | `ivr` | Routes digit: `1` → redirect to `/voicemail`, else re-prompt |
| `POST /voicemail` | `voicemail` | Says "leave a message after the beep", starts `<Record>` |
| `POST /voicemail/done` | `voicemail` | Hangs up |
| `POST /voicemail/callback` | `voicemail` | Downloads WAV → local disk → Google Drive → SQLite log → Slack notification → delete from Twilio |

**Security headers (`app/utils/security_headers.py`):**

Applied to every response via `app.after_request`:

| Header | Value |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'; form-action 'none'` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |

**Request validation:** All routes are decorated with `@validate_twilio_request` (`app/utils/twilio_validator.py`) — verifies the `X-Twilio-Signature` header against `TWILIO_AUTH_TOKEN` to reject spoofed requests.

**IVR Greeting Audio (`app/utils/audio_shuffle.py`):**

IVR greeting MP3 clips are hosted on Twilio Assets (visibility: Protected) at the URL configured in `TWILIO_ASSET_BASE`. Filenames are configured via `TWILIO_GREETING_CLIPS` (comma-separated, stored in `.env`). Clips were generated using [fish.audio](https://fish.audio/app).

The shuffle queue (`audio_shuffle.py`) exhausts all clips before repeating, resetting on container restart. Source MP3 files are stored locally outside the repo (not committed).

### Google Drive

| Component | Version | Purpose | Docs |
|---|---|---|---|
| **google-api-python-client** | 2.197.0 | Drive API v3 client | https://googleapis.github.io/google-api-python-client/ |
| **google-auth** | 2.55.0 | Service account credentials | https://google-auth.readthedocs.io/ |

**Helper (`app/gdrive.py`):**
- Authenticates with a service account JSON file (scope: `drive`)
- `upload_recording(local_path, filename)` → uploads WAV to the configured Shared Drive, returns Drive file ID
- Uses `supportsAllDrives=True` and `driveId` in metadata to target the Shared Drive root
- GDrive upload failure is non-fatal: logged as a warning, local copy kept, Twilio callback still returns 204

### Database (SQLite)

| File | Location |
|---|---|
| `ivr.db` | `./data/ivr.db` (inside Docker volume `./data`) |

**`recordings` table:**

| Column | Type | Purpose |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `created_at` | TEXT | ISO-8601 UTC timestamp |
| `caller_id` | TEXT | Caller's phone number (from Twilio `From`) |
| `duration` | INTEGER | Recording length in seconds |
| `filename` | TEXT | Recording filename (e.g. `Caller-23JUN2026-4-41PM.wav`) |
| `file_size` | INTEGER | Bytes |
| `twilio_sid` | TEXT | Twilio `RecordingSid` |
| `gdrive_file_id` | TEXT | Google Drive file ID (null if upload failed) |

Recordings are saved locally under `./data/recordings/YYYY/MM/DD/` and mirrored to Drive.

### Notifications

**Slack (`app/utils/slack.py`):**

After each successful voicemail save, the app posts a message to a configured Slack channel via an incoming webhook. The message includes:
- Caller's friendly name (from `CALLER_NAMES`)
- Timestamp of the recording (Eastern time)
- Duration in seconds
- Direct link to the file in Google Drive (`https://drive.google.com/file/d/{file_id}/view`)

The webhook is configured via `SLACK_WEBHOOK_URL` in `.env`. If the variable is unset, notifications are silently skipped — no error is raised. Slack failures are logged as warnings and do not affect the recording save or Twilio callback response.

---

## CI/CD Pipeline

### GitHub Actions (`.github/workflows/security.yml`)

Runs on every push to `main` and every pull request.

| Job | Tool | What it Checks | When |
|---|---|---|---|
| **Dependency Audit** | `pip-audit` | CVEs in `requirements.txt` against the OSV database | PRs + main |
| **Python SAST** | `bandit` + `ruff` | Hardcoded secrets, unsafe deserialization, injection risks, code quality | PRs + main |
| **Dockerfile Lint** | `hadolint` | Dockerfile best-practice violations | PRs + main |
| **Secret Scan** | `trufflehog` | Leaked credentials in full git history (verified-only) | PRs + main |
| **Container Scan** | `grype` (Anchore) | OS-level and library CVEs in the built Docker image — fails on fixable high/critical (`only-fixed: true`) | main only |

Container scan is gated to `main`-push only (slow Docker build); all other checks run on every PR.

### Action Pins

| Action | Version |
|---|---|
| `actions/checkout` | v7 |
| `actions/setup-python` | v6 |
| `trufflesecurity/trufflehog` | v3.95.6 |
| `hadolint/hadolint-action` | v3.3.0 |
| `anchore/scan-action` | v7 |

### GitHub Security Features

| Feature | Purpose |
|---|---|
| **Dependabot Alerts** | Notifies when dependencies have known CVEs |
| **Dependabot Security Updates** | Auto-opens PRs to bump vulnerable packages |
| **Dependabot Version Updates** | Weekly PRs for pip and GitHub Actions pins (grouped patch/minor) |

### External Security Scanning

[Aikido](https://aikido.dev) continuously scans `https://beabeacallme.siler.cloud` for web application vulnerabilities (missing security headers, exposed endpoints, misconfigurations, etc.).

### Uptime Monitoring

[UptimeRobot](https://uptimerobot.com) monitors `https://beabeacallme.siler.cloud/health` on the free tier (5-minute ping interval).

### Deployment Workflow

1. Create a feature branch (`feat/`, `fix/`, `ci/`, `chore/`)
2. Make changes and commit; update `Full-Stack-Documentation.md` version history
3. Push and open a PR — all checks run automatically
4. Merge PR on GitHub (never push directly to main)
5. Container scan runs on the merged main push
6. `git checkout main && git pull` on the host to fetch the merged changes
7. `docker compose down && docker compose up -d --build` on the host to deploy

---

## Configuration Reference

All configuration is via environment variables in `.env` (git-ignored).

### Required

| Variable | Purpose | Example |
|---|---|---|
| `TWILIO_ACCOUNT_SID` | Twilio account SID | `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| `TWILIO_AUTH_TOKEN` | Twilio auth token (also used for request validation) | `your_auth_token_here` |
| `TWILIO_PHONE_NUMBER` | Twilio phone number | `+15550000000` |
| `TWILIO_ASSET_BASE` | Twilio Assets service base URL (no trailing slash) | `https://your-service-name.twil.io` |
| `TWILIO_GREETING_CLIPS` | Comma-separated MP3 filenames hosted on Twilio Assets | `greeting-01.mp3,greeting-02.mp3` |
| `BASE_URL` | Public tunnel URL (no trailing slash) | `https://your-tunnel.your-domain.com` |
| `CLOUDFLARE_TUNNEL_TOKEN` | Cloudflare tunnel token for cloudflared container | (from Cloudflare dashboard) |
| `FLASK_SECRET_KEY` | Flask session secret — generate with `python -c "import secrets; print(secrets.token_hex(32))"` | (long random string) |
| `ALLOWED_CALLERS` | Comma-separated E.164 numbers permitted to call in; empty = allow all callers | `+15551234567,+15559876543` |
| `CALLER_NAMES` | Comma-separated `E.164:Name` pairs for friendly filenames | `+15550001111:Bea,+15550002222:Dustin` |
| `GDRIVE_CREDENTIALS_PATH` | Path to service account JSON inside container | `/app/secrets/your-credentials-file.json` |
| `GDRIVE_FOLDER_ID` | Shared Drive ID to upload recordings into | `0ABCDEFGHIJKLMNOPabcd` |
| `SLACK_WEBHOOK_URL` | Slack incoming webhook URL for new voicemail notifications (optional) | `https://hooks.slack.com/services/...` |

### Optional

| Variable | Default | Purpose |
|---|---|---|
| `DATA_DIR` | `./data` (relative to app root) | SQLite DB and recordings directory |

---

## Project Structure

```
BeaBeaCallMe/
├── .github/
│   ├── dependabot.yml                # Dependabot (pip + Actions — weekly, grouped)
│   └── workflows/
│       └── security.yml              # CI security pipeline
├── app/
│   ├── __init__.py                   # create_app() factory, blueprint registration, /health
│   ├── gdrive.py                     # Google Drive upload helper (service account)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── ivr.py                    # /call and /call/route — main menu
│   │   └── voicemail.py              # /voicemail, /voicemail/done, /voicemail/callback
│   ├── services/
│   │   └── __init__.py
│   └── utils/
│       ├── __init__.py
│       ├── audio_shuffle.py          # Shuffle queue for Twilio-hosted greeting MP3s
│       ├── db.py                     # SQLite init and log_recording()
│       ├── security_headers.py       # after_request security header injection
│       ├── twilio_validator.py       # @validate_twilio_request decorator
│       └── twiml.py                  # TwiML helper builders
├── data/
│   └── .gitkeep                      # Placeholder — SQLite DB and recordings live here
├── scripts/                          # (empty — recover.sh removed in v1.7.0)
├── .env                              # Secrets — git-ignored
├── .env.template                     # Template with all config keys
├── .gitignore
├── CLAUDE.md                         # Project instructions for Claude Code
├── docker-compose.yml                # Two-service compose: app + cloudflared (127.0.0.1:8080, ./data volume)
├── Dockerfile                        # python:3.13-slim + gunicorn
├── Full-Stack-Documentation.md       # This file
├── requirements.txt                  # Python dependencies
└── run.py                            # App entry point (create_app())
```

---

## Version History

| Tag | Date | Description |
|---|---|---|
| **v1.0.0** | 2026-06-22 | Initial setup: Docker + docker-compose, Google Drive upload via service account, SQLite gdrive_file_id column, CLAUDE.md, Full-Stack-Documentation.md |
| **v1.1.0** | 2026-06-22 | CI security pipeline: pip-audit, Bandit + Ruff, Hadolint, TruffleHog (PRs + main), Grype container scan (main only); Dependabot for pip and Actions |
| **v1.1.1** | 2026-06-22 | Bump python-dotenv 1.2.1→1.2.2 (CVE-2026-28684), requests 2.32.5→2.33.0 (CVE-2026-25645) |
| **v1.2.0** | 2026-06-22 | Dependabot batch: twilio 9.10.5→9.10.9, requests 2.33.0→2.34.2, google-api-python-client 2.169.0→2.197.0, google-auth 2.40.3→2.55.0, actions/checkout v4→v7, actions/setup-python v5→v6, trufflehog v3.88.26→v3.95.6, hadolint-action v3.1.0→v3.3.0, anchore/scan-action v6→v7; fix conflict markers in docs |
| **v1.2.1** | 2026-06-22 | Upgrade Python 3.12→3.13 (resolves CVE-2026-6100 Critical, CVE-2026-7210/4224/3644 High); add `only-fixed: true` to Grype to suppress unfixable Debian OS-level vulns |
| **v1.3.0** | 2026-06-22 | Add Cloudflare tunnel: `cloudflared` service in docker-compose, named tunnel `beabeacallme` routing `https://beabeacallme.siler.cloud` → `http://app:8080`; `CLOUDFLARE_TUNNEL_TOKEN` env var |
| **v1.3.1** | 2026-06-23 | Add caller allowlist: `ALLOWED_CALLERS` env var; unknown callers are rejected via `<Reject>` TwiML before hearing the IVR |
| **v1.4.0** | 2026-06-23 | Fix GDrive upload: switch to Shared Drive (`BeaBea-Tincan-Audio`), `drive` scope, `supportsAllDrives=True`; move credentials file to `C:\dev\BeaBeaCallMe\` to fix Docker bind-mount issue on Google Drive virtual filesystem; add `.dockerignore` |
| **v1.5.0** | 2026-06-23 | IVR greeting shuffle: replace `<Say>` with `<Play>` using MP3s hosted on Twilio Assets; shuffle queue exhausts all clips before repeating; recording saves on hang-up (`finish_on_key=""`) |
| **v1.5.1** | 2026-06-23 | Friendly recording filenames: `CALLER_NAMES` env var maps E.164 numbers to names; files named `Ashley-23JUN2026-4-41PM.wav` instead of timestamp+SID |
| **v1.5.2** | 2026-06-23 | Fix caller ID in recording callback (pass via query param); fix timestamp timezone to America/New_York |
| **v1.5.3** | 2026-06-23 | Fix caller name lookup: URL-encode `+` in E.164 numbers passed as query param (`+` decodes as space otherwise) |
| **v1.5.4** | 2026-06-23 | Strip whitespace from caller_id before CALLER_NAMES lookup (decoded `+` leaves a leading space) |
| **v1.6.0** | 2026-06-23 | Add security response headers (X-Content-Type-Options, X-Frame-Options, Referrer-Policy, CSP); document fish.audio IVR greeting clips |
| **v1.6.1** | 2026-06-23 | Document UptimeRobot uptime monitoring (free tier, 5-min ping) |
| **v1.6.2** | 2026-06-23 | Add `git pull` step to deployment workflow in docs |
| **v1.7.0** | 2026-06-23 | Security hardening: move Twilio asset base URL to `TWILIO_ASSET_BASE` env var; make `FLASK_SECRET_KEY` required; sanitize caller name before filesystem use; remove uptime from `/health`; add HSTS header; add `CLAUDE.md` to `.gitignore`; delete obsolete `recover.sh`; rewrite `.env.template` |
| **v1.7.1** | 2026-06-23 | Security pass 2: sanitize caller before logging (log injection); URL-encode caller in callback URL; thread-safe audio shuffle queue; pin cloudflared to 2026.6.1; remove TruffleHog --only-verified |
| **v1.7.2** | 2026-06-23 | Move IVR greeting clip filenames to `TWILIO_GREETING_CLIPS` env var; remove character names from source and docs |
| **v1.8.0** | 2026-06-24 | Pre-publication: anonymize doc (remove personal names and instance-specific URLs); add README, SECURITY.md; branch protection; disable wiki and issues; enable vulnerability alerts |
| **v1.9.0** | 2026-06-24 | Slack notifications: post to a configured channel when a new voicemail arrives, including caller name, timestamp, duration, and a direct Google Drive link; `SLACK_WEBHOOK_URL` env var (optional) |
| **v1.9.1** | 2026-06-24 | Fix CSP header: add explicit `frame-ancestors 'none'` and `form-action 'none'` directives (do not inherit from `default-src`); update doc CSP table and add Notifications section |
| **v1.9.2** | 2026-06-24 | Pin all GitHub Actions to commit SHAs; add non-root `appuser` to Dockerfile; validate recording URL is a `.twilio.com` host before fetching (SSRF mitigation) |
| **v1.9.3** | 2026-06-24 | Fix data volume permissions: add `entrypoint.sh` + `gosu` to `chown /app/data` to `appuser` at container start before handing off to gunicorn |
