# YouTube Shorts Uploader

I run multiple YouTube channels and uploading manually gets old fast. This Flask app connects to the YouTube API, lets you manage several accounts, and schedules uploads across time windows automatically.

## Features

- **Multi-account** — manage several YouTube channels from one dashboard
- **Playlist management** — organize videos into playlists with per-playlist captions
- **Smart scheduling** — distributes uploads across configurable time windows (morning, evening, etc.)
- **OAuth2 auth** — each account authenticates via Google OAuth, credentials stored locally
- **Upload log** — real-time log of upload status per video/account

## Tech stack

- Python 3 · Flask
- YouTube Data API v3 (`google-api-python-client`)
- `google-auth-oauthlib` for OAuth flow
- Jinja2 templates

## Getting started

```bash
pip install -r requirements.txt
python app.py
```

Open [http://localhost:5000](http://localhost:5000)

### Setup

1. Create a Google Cloud project, enable YouTube Data API v3
2. Download `client.json` (OAuth 2.0 credentials) and place it in the root
3. Add channel folders under `accounts/`
4. Put video playlists under `playlists/<name>/`
5. Authenticate each account from the dashboard

## Project structure

```
accounts/          # one folder per YouTube channel
playlists/         # video + caption sets
  └─ my-playlist/
       ├─ config.json
       ├─ captions.txt
       └─ videos/
app.py             # Flask app + upload logic
schedule.py        # scheduling logic
upload.py          # YouTube API wrapper
```
