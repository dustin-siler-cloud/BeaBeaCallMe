# BeaBeaCallMe — Full Stack Reference

> **Version:** v2.1.0
> **Last Updated:** 2026-06-30
> **Repo:** https://github.com/dustin-siler-cloud/BeaBeaCallMe
> **Purpose:** Self-hosted IVR voicemail so Bea (age 5) can call a Twilio number from her Tin Can kids' phone and leave voicemails that save to Google Drive.

---

## Monthly Costs

| Service | Cost | Notes |
|---|---|---|
| **Twilio phone number** | ~$1.15/mo | Required — inbound voice number |
| **Twilio inbound calls** | ~$0.0085/min | Negligible at typical usage (a few short calls/mo) |
| **Twilio outbound calls** | ~$0.014/min | Group call participant legs; negligible at typical usage |
| **Twilio SMS notifications** | ~$0.0079/message | One per `SMS_NOTIFY_NUMBERS` recipient per voicemail; negligible at typical usage |
| **Cloudflare Tunnel** | Free | Named tunnel, no bandwidth cap for this use case |
| **Google Drive** | Free | Storage via existing Google account |
| **GitHub** | Free | Public repo |
| **Tin Can Party Line** | $9.99/mo | **Optional** — subscription that enables the Tin Can kids' phone to make outbound calls; this project works with any phone as long as its number is `BEA_CALLER_ID` or in `FRIEND_CALLERS` |

**Estimated required spend: ~$1.15/mo.** The Tin Can subscription is optional and independent of this project.

---

## Table of Contents

- [Monthly Costs](#monthly-costs)
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

Any inbound caller hits Twilio → Twilio posts to `/call` → the app looks up the caller's role (`bea`, `friend`, or rejected) and plays a role-specific menu. Bea's menu offers voicemail (1) and a group call (6); the friend menu offers voicemail only (1). Voicemails are downloaded, saved locally, uploaded to a role-specific Google Drive subfolder, logged to SQLite, and trigger an SMS notification. The group call drops Bea into a Twilio conference room and dials out to configured participants.

```
  Bea's phone          Friend's phone
         │  PSTN call          │  PSTN call
         ▼                     ▼
  ┌─────────────────────────────────┐
  │            Twilio                │  Managed phone number (~$1.15/mo)
  └──────────────┬───────────────────┘
                  │  HTTPS webhooks (TwiML)
                  ▼
  ┌─────────────────────┐
  │  Cloudflare Tunnel  │  Named tunnel — no open inbound ports
  └──────────┬──────────┘
             │  HTTP → localhost:8080
             ▼
  ┌─────────────────────────────────────────┐
  │   Windows 11 Gaming PC                  │
  │                                         │
  │   Docker → Flask app :8080              │
  │     /call            role-based menu    │
  │     /call/route      digit routing      │
  │     /voicemail       start recording    │
  │     /voicemail/done  hang up            │
  │     /voicemail/callback                 │
  │       ├─ download WAV from Twilio       │
  │       ├─ save to ./data/recordings/     │
  │       ├─ upload to Google Drive         │
  │       │    (From Bea or To Bea folder)  │
  │       ├─ log to SQLite                  │
  │       ├─ send SMS notification           │
  │       └─ delete from Twilio             │
  │     /conference       Bea joins room,   │
  │                        dials out to     │
  │                        participants     │
  │     /conference/join  participant leg   │
  │                        joins room       │
  └─────────────────────────────────────────┘
         │  Google Drive API (service account)
         ▼
  ┌──────────────────────────┐
  │  Google Drive             │  "From Bea" / "To Bea" subfolders
  └──────────────────────────┘
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
The app runs as `appuser` (no password, no shell). An `entrypoint.sh` script runs first as root to `chown /app/data` to `appuser` (the bind-mounted `./data` volume arrives owned by root), then uses Python's `os.setuid`/`os.setgid` to drop privileges before exec-ing gunicorn. No external privilege-drop utility is required, avoiding Go stdlib CVEs that would otherwise appear in container scans.

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

**Caller Roles (`app/utils/caller_role.py`):**

Every inbound call is classified before any menu plays:
- `bea` — caller matches `BEA_CALLER_ID` exactly
- `friend` — caller is in `FRIEND_CALLERS` (comma-separated)
- unrecognized — call is rejected via `<Reject>` before hearing any menu

**IVR Flow (`app/routes/`):**

| Route | Blueprint | What Happens |
|---|---|---|
| `POST /call` | `ivr` | Entry point — classifies caller role, plays role-specific menu (`bea`: press 1 or 6; `friend`: press 1 only) |
| `POST /call/route` | `ivr` | Routes digit by role: `1` → `/voicemail` (either role); `6` → `/conference` (`bea` only); anything else re-prompts |
| `POST /voicemail` | `voicemail` | Says "leave a message after the beep", starts `<Record>` |
| `POST /voicemail/done` | `voicemail` | Hangs up |
| `POST /voicemail/callback` | `voicemail` | Downloads WAV → local disk → Google Drive (role-specific subfolder) → SQLite log → SMS notification → delete from Twilio |
| `POST /conference` | `conference` | Bea joins a Twilio conference room; app dials out to `CONFERENCE_PARTICIPANTS` |
| `POST /conference/join` | `conference` | TwiML answered by each outbound participant leg — joins the same conference room |

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

IVR greeting MP3 clips are hosted on Twilio Assets (visibility: Protected) at the URL configured in `TWILIO_ASSET_BASE`. There are two independent clip sets and shuffle queues, one per caller role:
- `TWILIO_GREETING_CLIPS` — Bea's menu (mentions both voicemail and group call options)
- `TWILIO_FRIEND_GREETING_CLIPS` — friend menu (voicemail option only, no Bea-specific content)

Clips were generated using [fish.audio](https://fish.audio/app). Each shuffle queue exhausts all its clips before repeating, resetting on container restart. Source MP3 files are stored locally outside the repo (not committed).

**Group Call (`app/routes/conference.py`):**

When Bea presses 6, the app drops her into a named Twilio conference room (`<Dial><Conference>`) and places outbound calls via the Twilio REST API to every number in `CONFERENCE_PARTICIPANTS`. Each outbound leg answers with TwiML from `/conference/join`, which joins the same room. The conference ends when Bea hangs up (`end_conference_on_exit=True` on her leg only); a 10-minute hard cap (`time_limit`) prevents runaway calls. Participants who don't answer simply never join — no error surfaces to Bea.

### Google Drive

| Component | Version | Purpose | Docs |
|---|---|---|---|
| **google-api-python-client** | 2.197.0 | Drive API v3 client | https://googleapis.github.io/google-api-python-client/ |
| **google-auth** | 2.55.0 | Service account credentials | https://google-auth.readthedocs.io/ |

**Helper (`app/gdrive.py`):**
- Authenticates with a service account JSON file (scope: `drive`)
- `upload_recording(local_path, filename, folder_id)` → uploads WAV to the given subfolder, returns Drive file ID
- `driveId` (the Shared Drive root, `GDRIVE_FOLDER_ID`) and `parents` (the target subfolder) are set separately — `supportsAllDrives=True` is required for both
- GDrive upload failure is non-fatal: logged as a warning, local copy kept, Twilio callback still returns 204

**Subfolders:** recordings route to one of two subfolders within the Shared Drive based on caller role:
- `GDRIVE_FOLDER_ID_FROM_BEA` — voicemails Bea leaves for friends
- `GDRIVE_FOLDER_ID_TO_BEA` — voicemails friends leave for Bea

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

**SMS (`app/utils/sms.py`):**

After each successful voicemail save, the app sends a text message via the Twilio REST API to every number in `SMS_NOTIFY_NUMBERS`. The message includes:
- Direction ("from Bea" or "for Bea (from {caller name})")
- Timestamp of the recording (Eastern time)
- Duration in seconds
- Direct link to the file in Google Drive (`https://drive.google.com/file/d/{file_id}/view`)

If `SMS_NOTIFY_NUMBERS` is unset, notifications are silently skipped — no error is raised. A failed send to one recipient is logged as a warning and does not block sending to the others or affect the recording save / Twilio callback response.

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
| `TWILIO_GREETING_CLIPS` | Comma-separated MP3 filenames hosted on Twilio Assets — Bea's menu | `greeting-01.mp3,greeting-02.mp3` |
| `TWILIO_FRIEND_GREETING_CLIPS` | Comma-separated MP3 filenames hosted on Twilio Assets — friend menu | `friend-greeting-01.mp3` |
| `BASE_URL` | Public tunnel URL (no trailing slash) | `https://your-tunnel.your-domain.com` |
| `CLOUDFLARE_TUNNEL_TOKEN` | Cloudflare tunnel token for cloudflared container | (from Cloudflare dashboard) |
| `FLASK_SECRET_KEY` | Flask session secret — generate with `python -c "import secrets; print(secrets.token_hex(32))"` | (long random string) |
| `BEA_CALLER_ID` | Single E.164 number that routes to Bea's IVR menu (voicemail + group call) | `+15550001111` |
| `FRIEND_CALLERS` | Comma-separated E.164 numbers that route to the friend IVR menu (voicemail only) | `+15550002222,+15550003333` |
| `CONFERENCE_PARTICIPANTS` | Comma-separated E.164 numbers Twilio dials when Bea starts a group call | `+15550002222,+15550003333` |
| `CALLER_NAMES` | Comma-separated `E.164:Name` pairs for friendly filenames | `+15550001111:Bea,+15550002222:Dustin` |
| `GDRIVE_CREDENTIALS_PATH` | Path to service account JSON inside container | `/app/secrets/your-credentials-file.json` |
| `GDRIVE_FOLDER_ID` | Shared Drive ID (root) | `0ABCDEFGHIJKLMNOPabcd` |
| `GDRIVE_FOLDER_ID_FROM_BEA` | Subfolder ID for voicemails Bea leaves for friends | `1ABCDEFGHIJKLMNOPabcd` |
| `GDRIVE_FOLDER_ID_TO_BEA` | Subfolder ID for voicemails friends leave for Bea | `1ZYXWVUTSRQPONMabcd` |
| `SMS_NOTIFY_NUMBERS` | Comma-separated E.164 numbers to text on new voicemail (optional) | `+15550001111,+15550002222` |

> **Keep `CONFERENCE_PARTICIPANTS` and `FRIEND_CALLERS` in sync:** anyone added to the group call list should also be able to call in and leave Bea a voicemail, so add new numbers to both lists together unless told otherwise for a specific person.

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
| **v1.9.4** | 2026-06-24 | Replace `gosu` with Python `os.setuid`/`os.setgid` in `entrypoint.sh` to eliminate Go stdlib CVEs introduced by the gosu binary |
| **v1.9.5** | 2026-06-25 | Fix `entrypoint.sh` CRLF line endings: Windows git checkout converts LF→CRLF making the shebang unparseable on Linux; strip in Dockerfile `RUN sed` and add `.gitattributes eol=lf` |
| **v1.9.6** | 2026-06-25 | Add Monthly Costs section at top of doc |
| **v2.0.0** | 2026-06-30 | Caller-role IVR routing: `BEA_CALLER_ID`/`FRIEND_CALLERS` replace `ALLOWED_CALLERS`; Bea's menu gets a new "press 6" group call option; friends get a voicemail-only menu; new `/conference` + `/conference/join` routes dial out to `CONFERENCE_PARTICIPANTS` via Twilio `<Dial><Conference>`; recordings route to role-specific Google Drive subfolders (`GDRIVE_FOLDER_ID_FROM_BEA` / `GDRIVE_FOLDER_ID_TO_BEA`); separate greeting clip shuffle queues per role (`TWILIO_GREETING_CLIPS` / `TWILIO_FRIEND_GREETING_CLIPS`) |
| **v2.1.0** | 2026-06-30 | Replace Slack notifications with SMS via Twilio (`SMS_NOTIFY_NUMBERS`, `app/utils/sms.py`); remove `app/utils/slack.py` and `SLACK_WEBHOOK_URL`; remove "leave a message after the beep" TTS prompt — recording now starts straight to the beep |
