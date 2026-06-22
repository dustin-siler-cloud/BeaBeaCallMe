# BeaBeaCallMe — Project Instructions

## What This Is
Self-hosted IVR voicemail for Bea's Tin Can kids' phone. Bea calls a Twilio number → presses 1 → leaves a message → recording uploads to Google Drive.

## Local Directory
`G:\My Drive\ClaudeCode\BeaBeaCallMe\`

## Deployment
- Docker on Windows 11 gaming PC, port bound to `127.0.0.1:8080`
- Exposed publicly via named Cloudflare tunnel → `localhost:8080`
- Start/rebuild: `docker compose up -d --build` (from project root)

## Workflow
- **Branch workflow:** Create a feature branch at the start of each session (`feat/`, `fix/`, `ci/`, `chore/`). Push and open a PR at the end. User merges on GitHub — no direct pushes to main.
- When pushing, always update `Full-Stack-Documentation.md` with a new version history entry and bump the version/date at the top of the file.

## Secrets (never commit)
- `.env` — Twilio credentials, BASE_URL, Flask secret key, GDrive config
- `gdrive-credentials.json` — Google service account key (mount read-only into container)

## Key Files
- `app/gdrive.py` — Google Drive upload helper (service account)
- `app/routes/voicemail.py` — Twilio IVR routes; `/voicemail/callback` triggers GDrive upload
- `app/utils/db.py` — SQLite init and recording log
- `config.py` — All env var config (fails fast on missing required vars)
