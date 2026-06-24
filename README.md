# BeaBeaCallMe

Self-hosted IVR voicemail system for a kids' phone. A child calls a Twilio number, presses 1, leaves a message, and the recording is automatically saved to Google Drive.

## How it works

```
Child's phone → Twilio (IVR) → Cloudflare Tunnel → Flask app → Google Drive
```

- Twilio handles the inbound call and plays a randomized greeting clip
- The caller presses 1 and leaves a message; recording saves on hang-up
- The Flask app downloads the WAV, saves it locally, and uploads it to a Google Shared Drive
- Recordings are named by caller (e.g. `Bea-24JUN2026-3-15PM.wav`) using a configurable name map

## Stack

- **Flask** + **Gunicorn** — IVR webhook handler
- **Twilio** — managed phone number, TwiML IVR, recording
- **Twilio Assets** — hosts MP3 greeting clips (protected visibility)
- **Google Drive API** — uploads recordings to a Shared Drive via service account
- **Cloudflare Tunnel** — exposes the local app publicly without open ports
- **Docker + Docker Compose** — containerized deployment
- **SQLite** — local recording metadata log

## Quick start

1. **Clone and configure**

   ```bash
   git clone https://github.com/dustin-siler-cloud/BeaBeaCallMe.git
   cd BeaBeaCallMe
   cp .env.template .env
   # Fill in all values in .env
   ```

2. **Set up prerequisites**
   - A [Twilio](https://twilio.com) account with a phone number and a Functions/Assets service for hosting MP3 greeting clips
   - A Google Cloud service account with access to a Google Shared Drive
   - A [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) configured to route your public hostname to `http://app:8080`

3. **Place credentials**

   Put your Google service account JSON key somewhere on your local filesystem (outside any cloud-synced directory) and update the volume mount path in `docker-compose.yml`.

4. **Run**

   ```bash
   docker compose up -d --build
   ```

5. **Configure Twilio webhook**

   Point your Twilio number's incoming voice webhook to `https://your-public-hostname/call` (HTTP POST).

See [`Full-Stack-Documentation.md`](Full-Stack-Documentation.md) for the complete reference.

## Security

All Twilio webhook routes are validated via `X-Twilio-Signature`. Inbound callers are filtered by an allowlist (`ALLOWED_CALLERS`). Credentials never touch the repo — see [`.env.template`](.env.template) for the full configuration surface.

To report a security vulnerability, see [`SECURITY.md`](SECURITY.md).

## License

No license is currently specified. All rights reserved.
