# BeaBeaCallMe — Full Stack Reference

<<<<<<< HEAD
> **Version:** v1.1.1
=======
> **Version:** v1.0.1
>>>>>>> 8d86ef2 (fix: bump python-dotenv and requests to patch CVEs)
> **Last Updated:** 2026-06-22
> **Repo:** https://github.com/dustin-siler-cloud/BeaBeaCallMe (private)
> **Purpose:** Self-hosted IVR voicemail so Bea (age 5) can call a Twilio number from her Tin Can kids' phone and leave voicemails that save to Google Drive.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Infrastructure](#infrastructure)
- [Backend Stack](#backend-stack)
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
  │     /voicemail/done  say goodbye    │
  │     /voicemail/callback             │
  │       ├─ download WAV from Twilio   │
  │       ├─ save to ./data/recordings/ │
  │       ├─ upload to Google Drive     │
  │       ├─ log to SQLite              │
  │       └─ delete from Twilio         │
  └─────────────────────────────────────┘
         │  Google Drive API (service account)
         ▼
  ┌─────────────────┐
  │  Google Drive   │  Shared folder — Dustin can listen from any device
  └─────────────────┘
```

---

## Infrastructure

### Docker

| Component | Image | Purpose |
|---|---|---|
| **App** | `python:3.12-slim` | Flask IVR app + GDrive uploader |

**Compose:**
- `docker-compose.yml` — single service, port bound to `127.0.0.1:8080`, `./data` volume for SQLite persistence, `gdrive-credentials.json` mounted read-only.

**Start/rebuild:**
```bash
docker compose up -d --build
```

### Networking

| Exposure | How |
|---|---|
| Public HTTPS | Cloudflare named tunnel (outbound-only, no open ports) |
| App port | `127.0.0.1:8080` (localhost-only bind) |
| TLS | Terminated by Cloudflare edge |

### Cloudflare Tunnel

The tunnel is configured externally (same pattern as SecScan). The app only needs `BASE_URL` set to the tunnel's public hostname so Twilio can construct callback URLs.

---

## Backend Stack

### Runtime

| Component | Version | Purpose | Docs |
|---|---|---|---|
| **Python** | 3.12 | Runtime | https://docs.python.org/3.12/ |
| **Flask** | 3.1.3 | Web framework | https://flask.palletsprojects.com/ |
| **Gunicorn** | latest | WSGI server (2 workers, 60s timeout) | https://docs.gunicorn.org/ |
| **python-dotenv** | 1.2.2 | `.env` loading | https://github.com/theskumar/python-dotenv |

### Twilio

| Component | Version | Purpose | Docs |
|---|---|---|---|
| **twilio** | 9.10.5 | Twilio REST client + TwiML builder | https://www.twilio.com/docs/libraries/python |
| **requests** | 2.33.0 | Download recordings from Twilio | https://docs.python-requests.org/ |

**IVR Flow (`app/routes/`):**

| Route | Blueprint | What Happens |
|---|---|---|
| `POST /call` | `ivr` | Entry point — plays main menu ("press 1 to leave a voicemail") |
| `POST /call/route` | `ivr` | Routes digit: `1` → redirect to `/voicemail`, else re-prompt |
| `POST /voicemail` | `voicemail` | Says "leave a message after the beep", starts `<Record>` |
| `POST /voicemail/done` | `voicemail` | Says "thank you, goodbye", hangs up |
| `POST /voicemail/callback` | `voicemail` | Downloads WAV → local disk → Google Drive → SQLite log → delete from Twilio |

**Request validation:** All routes are decorated with `@validate_twilio_request` (`app/utils/twilio_validator.py`) — verifies the `X-Twilio-Signature` header against `TWILIO_AUTH_TOKEN` to reject spoofed requests.

### Google Drive

| Component | Version | Purpose | Docs |
|---|---|---|---|
| **google-api-python-client** | 2.169.0 | Drive API v3 client | https://googleapis.github.io/google-api-python-client/ |
| **google-auth** | 2.40.3 | Service account credentials | https://google-auth.readthedocs.io/ |

**Helper (`app/gdrive.py`):**
- Authenticates with a service account JSON file (scope: `drive.file`)
- `upload_recording(local_path, filename)` → uploads WAV to the configured Drive folder, returns Drive file ID
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
| `filename` | TEXT | Relative path under `recordings/` (e.g. `2026/06/22/2026-06-22_14-30-00_RExxxx.wav`) |
| `file_size` | INTEGER | Bytes |
| `twilio_sid` | TEXT | Twilio `RecordingSid` |
| `gdrive_file_id` | TEXT | Google Drive file ID (null if upload failed) |

Recordings are saved locally under `./data/recordings/YYYY/MM/DD/` and mirrored to Drive.

---

## CI/CD Pipeline

### GitHub Actions (`.github/workflows/security.yml`)

Runs on every push to `main` and every pull request.

| Job | Tool | What it Checks | When |
|---|---|---|---|
| **Dependency Audit** | `pip-audit` | CVEs in `requirements.txt` against the OSV database | PRs + main |
| **Python SAST** | `bandit` + `ruff` | Hardcoded secrets, unsafe deserialization, injection risks, code quality | PRs + main |
| **Dockerfile Lint** | `hadolint` | Dockerfile best-practice violations | PRs + main |
| **Secret Scan** | `trufflehog` | Leaked credentials in full git history (verified-only) | main only |
| **Container Scan** | `grype` (Anchore) | OS-level and library CVEs in the built Docker image — fails on fixable high/critical | main only |

Secret scan and container scan are gated to `main`-push only to keep PR feedback fast.

### GitHub Security Features

| Feature | Purpose |
|---|---|
| **Dependabot Alerts** | Notifies when dependencies have known CVEs |
| **Dependabot Security Updates** | Auto-opens PRs to bump vulnerable packages |
| **Dependabot Version Updates** | Weekly PRs for pip and GitHub Actions pins (grouped patch/minor) |

### Deployment Workflow

1. Create a feature branch (`feat/`, `fix/`, `ci/`, `chore/`)
2. Make changes and commit; update `Full-Stack-Documentation.md` version history
3. Push and open a PR — dependency audit, SAST, and Dockerfile lint run automatically
4. Merge PR on GitHub (never push directly to main)
5. Secret scan and container scan run on the merged main push
6. `docker compose up -d --build` on the host to deploy

---

## Configuration Reference

All configuration is via environment variables in `.env` (git-ignored).

### Required

| Variable | Purpose | Example |
|---|---|---|
| `TWILIO_ACCOUNT_SID` | Twilio account SID | `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| `TWILIO_AUTH_TOKEN` | Twilio auth token (also used for request validation) | `your_auth_token_here` |
| `TWILIO_PHONE_NUMBER` | Twilio phone number | `+15550000000` |
| `BASE_URL` | Public tunnel URL (no trailing slash) | `https://bea-voicemail.your-tunnel.com` |
| `GDRIVE_CREDENTIALS_PATH` | Path to service account JSON inside container | `/app/gdrive-credentials.json` |
| `GDRIVE_FOLDER_ID` | Google Drive folder ID to upload recordings into | `1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs` |

### Optional

| Variable | Default | Purpose |
|---|---|---|
| `DATA_DIR` | `./data` (relative to app root) | SQLite DB and recordings directory |
| `FLASK_SECRET_KEY` | `dev-secret-change-me` | Flask session secret — change in production |

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
│       ├── db.py                     # SQLite init and log_recording()
│       ├── twilio_validator.py       # @validate_twilio_request decorator
│       └── twiml.py                  # TwiML helper builders
├── data/
│   └── .gitkeep                      # Placeholder — SQLite DB and recordings live here
├── scripts/
│   └── recover.sh                    # Upstream recovery script
├── .env                              # Secrets — git-ignored
├── .env.template                     # Template with all config keys
├── .gitignore
├── CLAUDE.md                         # Project instructions for Claude Code
├── docker-compose.yml                # Single-service compose (127.0.0.1:8080, ./data volume)
├── Dockerfile                        # python:3.12-slim + gunicorn
├── Full-Stack-Documentation.md       # This file
├── requirements.txt                  # Python dependencies
└── run.py                            # App entry point (create_app())
```

---

## Version History

| Tag | Date | Description |
|---|---|---|
| **v1.0.0** | 2026-06-22 | Initial setup: Docker + docker-compose, Google Drive upload via service account, SQLite gdrive_file_id column, CLAUDE.md, Full-Stack-Documentation.md |
<<<<<<< HEAD
| **v1.1.0** | 2026-06-22 | CI security pipeline: pip-audit, Bandit + Ruff, Hadolint, TruffleHog, Grype container scan; Dependabot for pip and Actions |
| **v1.1.1** | 2026-06-22 | Bump python-dotenv 1.2.1→1.2.2 (CVE-2026-28684), requests 2.32.5→2.33.0 (CVE-2026-25645) |
