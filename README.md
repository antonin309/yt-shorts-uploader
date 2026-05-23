# YouTube Shorts Uploader

Built a Flask app that handles scheduling and uploading via the YouTube API. First version comes with a Windows XP UI.

**Learned:** Python, Flask, YouTube Data API v3, OAuth2 flows


## Features

- **Multi-account** — manage several YouTube channels from one dashboard
- **Channel management** — organize videos into channel sub-topics 
- **Smart scheduling** — distributes uploads across configurable time windows (morning, evening, etc.)
- **OAuth2 auth** — each account authenticates via Google OAuth, credentials stored locally
- **Upload log** — real-time log of upload status per video/account

## Tech stack

- Python 3 · Flask
- YouTube Data API v3 (`google-api-python-client`)
- `google-auth-oauthlib` for OAuth flow
- Jinja2 templates


### Setup

1. Create a Google Cloud project, enable YouTube Data API v3
2. Download `client.json` (OAuth 2.0 credentials) and place it in the root
3. Add channel folders under `accounts/`
4. Put video playlists under `playlists/<name>/`
5. Authenticate each account from the dashboard

