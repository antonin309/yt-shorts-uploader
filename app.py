import os
import json
import glob
import random
import shutil
import threading
import subprocess
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import googleapiclient.discovery
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024

ACCOUNTS_FOLDER = "accounts"
PLAYLISTS_FOLDER = "playlists"

VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.flv', '.wmv', '.mts', '.m2ts'}

TIME_WINDOWS = [
    ("Early Morning", 5, 7),
    ("Morning", 7, 9),
    ("Late Morning", 9, 11),
    ("Midday", 11, 13),
    ("Afternoon", 13, 15),
    ("Late Afternoon", 15, 17),
    ("Evening", 17, 19),
    ("Night", 19, 21),
    ("Late Night", 21, 23),
]

upload_log = []
upload_running = False
connect_status = {}   # account_name -> 'running' | 'done' | 'error:...'


def get_accounts():
    if not os.path.exists(ACCOUNTS_FOLDER):
        return []
    return sorted([d for d in os.listdir(ACCOUNTS_FOLDER)
                   if os.path.isdir(os.path.join(ACCOUNTS_FOLDER, d))])


def get_playlists():
    if not os.path.exists(PLAYLISTS_FOLDER):
        return []
    return sorted([d for d in os.listdir(PLAYLISTS_FOLDER)
                   if os.path.isdir(os.path.join(PLAYLISTS_FOLDER, d))])


def playlist_path(name):
    return os.path.join(PLAYLISTS_FOLDER, name)


def load_playlist_config(name):
    path = os.path.join(playlist_path(name), "config.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_playlist_captions(name):
    path = os.path.join(playlist_path(name), "captions.txt")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def get_playlist_videos(name):
    folder = os.path.join(playlist_path(name), "videos")
    files = []
    for f in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if os.path.splitext(f)[1].lower() in VIDEO_EXTENSIONS:
            files.append(f)
    return files


def random_time_in_window(date, hour_start, hour_end):
    hour = random.randint(hour_start, hour_end - 1)
    minute = random.randint(0, 59)
    local_dt = datetime(date.year, date.month, date.day, hour, minute,
                        tzinfo=timezone(timedelta(hours=2)))
    utc_dt = local_dt.astimezone(timezone.utc)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_channel_info(account_name):
    token_path = os.path.join(ACCOUNTS_FOLDER, account_name, "token.json")
    cache_path = os.path.join(ACCOUNTS_FOLDER, account_name, "channel_info.json")

    if os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            return json.load(f)

    if not os.path.exists(token_path):
        return None

    try:
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)
        response = youtube.channels().list(part="snippet,statistics", mine=True).execute()
        if not response.get("items"):
            return None
        item = response["items"][0]
        info = {
            "channelName": item["snippet"]["title"],
            "channelId": item["id"],
            "thumbnail": item["snippet"]["thumbnails"].get("default", {}).get("url", ""),
            "subscribers": item["statistics"].get("subscriberCount", "?"),
            "email": item["snippet"].get("customUrl", ""),
        }
        with open(cache_path, "w") as f:
            json.dump(info, f)
        return info
    except Exception as e:
        return {"error": str(e)}


def get_playlists_by_account():
    result = {}
    for name in get_playlists():
        config = load_playlist_config(name)
        account = config.get("account", "")
        if account not in result:
            result[account] = []
        result[account].append({
            "id": name,
            "displayName": config.get("displayName", name),
        })
    return result


@app.route("/")
def index():
    return render_template("index.html",
                           accounts=get_accounts(),
                           playlists_by_account=get_playlists_by_account(),
                           today=datetime.now().strftime("%Y-%m-%d"))


@app.route("/playlist-info/<name>")
def playlist_info(name):
    config = load_playlist_config(name)
    captions = load_playlist_captions(name)
    videos = get_playlist_videos(name)
    return jsonify({"config": config, "captions": captions, "videos": videos})


@app.route("/upload-video/<playlist>", methods=["POST"])
def upload_video_file(playlist):
    folder = os.path.join(playlist_path(playlist), "videos")
    os.makedirs(folder, exist_ok=True)
    if "videos" not in request.files:
        return jsonify({"error": "No file"}), 400
    files = request.files.getlist("videos")
    uploaded = []
    for f in files:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext in VIDEO_EXTENSIONS:
            filename = secure_filename(f.filename)
            f.save(os.path.join(folder, filename))
            uploaded.append(filename)
    return jsonify({"uploaded": uploaded})


@app.route("/save-captions/<playlist>", methods=["POST"])
def save_captions(playlist):
    data = request.json
    captions = data.get("captions", [])
    path = os.path.join(playlist_path(playlist), "captions.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(captions))
    return jsonify({"ok": True})


@app.route("/save-config/<playlist>", methods=["POST"])
def save_config(playlist):
    data = request.json
    path = os.path.join(playlist_path(playlist), "config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True})


@app.route("/account-info/<name>")
def account_info(name):
    info = get_channel_info(name)
    return jsonify(info or {})


@app.route("/create-account", methods=["POST"])
def create_account():
    data = request.json
    name = data.get("name", "").strip().lower().replace(" ", "-")
    if not name:
        return jsonify({"error": "No name"}), 400
    os.makedirs(os.path.join(ACCOUNTS_FOLDER, name), exist_ok=True)
    return jsonify({"ok": True, "name": name})


@app.route("/connect-account/<name>", methods=["POST"])
def connect_account(name):
    if connect_status.get(name) == 'running':
        return jsonify({"error": "Already connecting"}), 400

    client_path = "client.json"
    if not os.path.exists(client_path):
        return jsonify({"error": "client.json not found"}), 500

    connect_status[name] = 'running'

    def run():
        try:
            flow = InstalledAppFlow.from_client_secrets_file(client_path, SCOPES)
            creds = flow.run_local_server(port=0, open_browser=True)
            folder = os.path.join(ACCOUNTS_FOLDER, name)
            os.makedirs(folder, exist_ok=True)
            token_path = os.path.join(folder, "token.json")
            with open(token_path, "w") as f:
                f.write(creds.to_json())
            # Clear old channel info cache
            cache_path = os.path.join(folder, "channel_info.json")
            if os.path.exists(cache_path):
                os.remove(cache_path)

            # Fetch all channels to detect multi-channel accounts
            youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)
            resp = youtube.channels().list(part="snippet,statistics", mine=True, maxResults=10).execute()
            items = resp.get("items", [])

            if len(items) == 1:
                # Only one channel — auto-select
                item = items[0]
                info = {
                    "channelName": item["snippet"]["title"],
                    "channelId": item["id"],
                    "thumbnail": item["snippet"]["thumbnails"].get("default", {}).get("url", ""),
                    "subscribers": item["statistics"].get("subscriberCount", "?"),
                }
                with open(cache_path, "w") as f:
                    json.dump(info, f)
                connect_status[name] = 'done'
            elif len(items) > 1:
                # Multiple channels — let user pick
                channels = []
                for item in items:
                    channels.append({
                        "channelId": item["id"],
                        "channelName": item["snippet"]["title"],
                        "thumbnail": item["snippet"]["thumbnails"].get("default", {}).get("url", ""),
                        "subscribers": item["statistics"].get("subscriberCount", "?"),
                    })
                connect_status[name] = 'channels:' + json.dumps(channels)
            else:
                connect_status[name] = 'error:No YouTube channel found for this Google account'
        except Exception as e:
            connect_status[name] = f'error:{e}'

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/connect-status/<name>")
def connect_status_route(name):
    return jsonify({"status": connect_status.get(name, 'idle')})


@app.route("/select-channel/<name>", methods=["POST"])
def select_channel(name):
    data = request.json
    channel_id = data.get("channelId", "")
    if not channel_id:
        return jsonify({"error": "No channelId"}), 400

    token_path = os.path.join(ACCOUNTS_FOLDER, name, "token.json")
    if not os.path.exists(token_path):
        return jsonify({"error": "No token found"}), 404

    try:
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)
        resp = youtube.channels().list(part="snippet,statistics", id=channel_id).execute()
        items = resp.get("items", [])
        if not items:
            return jsonify({"error": "Channel not found"}), 404
        item = items[0]
        info = {
            "channelName": item["snippet"]["title"],
            "channelId": item["id"],
            "thumbnail": item["snippet"]["thumbnails"].get("default", {}).get("url", ""),
            "subscribers": item["statistics"].get("subscriberCount", "?"),
        }
        cache_path = os.path.join(ACCOUNTS_FOLDER, name, "channel_info.json")
        with open(cache_path, "w") as f:
            json.dump(info, f)
        connect_status[name] = 'done'
        return jsonify({"ok": True, "info": info})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/delete-account/<name>", methods=["POST"])
def delete_account(name):
    folder = os.path.join(ACCOUNTS_FOLDER, name)
    if not os.path.exists(folder):
        return jsonify({"error": "Not found"}), 404
    shutil.rmtree(folder)
    return jsonify({"ok": True})


@app.route("/create-playlist", methods=["POST"])
def create_playlist():
    data = request.json
    name = data.get("name", "").strip().lower().replace(" ", "-")
    if not name:
        return jsonify({"error": "No name"}), 400
    folder = playlist_path(name)
    os.makedirs(os.path.join(folder, "videos"), exist_ok=True)
    config = {
        "account": data.get("account", ""),
        "displayName": data.get("displayName", name),
        "hashtags": "#Shorts",
        "tags": "",
        "privacy": "public",
        "language": "en"
    }
    with open(os.path.join(folder, "config.json"), "w") as f:
        json.dump(config, f, indent=2)
    with open(os.path.join(folder, "captions.txt"), "w") as f:
        f.write("")
    return jsonify({"ok": True, "name": name})


@app.route("/delete-playlist/<name>", methods=["POST"])
def delete_playlist(name):
    folder = playlist_path(name)
    if not os.path.exists(folder):
        return jsonify({"error": "Not found"}), 404
    shutil.rmtree(folder)
    return jsonify({"ok": True})


@app.route("/schedule", methods=["POST"])
def schedule():
    data = request.json
    playlists = data.get("playlists", [])
    if not playlists:
        pl = data.get("playlist")
        if pl:
            playlists = [pl]

    account = data.get("account")
    start_date_str = data.get("startDate")
    privacy = data.get("privacy", "public")
    caption_mode = data.get("captionMode", "random")
    fixed_caption = data.get("fixedCaption", "")
    random_times = data.get("randomTimes", True)
    made_for_kids = False
    active_slots = data.get("activeSlots", [1, 3, 6, 8])

    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    active_windows = [TIME_WINDOWS[i] for i in sorted(active_slots) if i < len(TIME_WINDOWS)]
    slots_per_day = len(active_windows)

    if not active_windows or not playlists:
        return jsonify({"error": "No time slots or subtopics selected"}), 400

    # Load per-playlist data
    captions_by_pl = {}
    config_by_pl = {}
    video_queues = []
    for pl in playlists:
        vid_folder = os.path.join(playlist_path(pl), "videos")
        videos = sorted([
            os.path.join(vid_folder, f) for f in os.listdir(vid_folder)
            if os.path.isdir(vid_folder) and os.path.splitext(f)[1].lower() in VIDEO_EXTENSIONS
        ]) if os.path.isdir(vid_folder) else []
        video_queues.append((pl, videos))
        captions_by_pl[pl] = load_playlist_captions(pl)
        config_by_pl[pl] = load_playlist_config(pl)

    # Round-robin interleave across subtopics so each day gets variety
    merged = []
    max_len = max((len(q) for _, q in video_queues), default=0)
    for i in range(max_len):
        for pl_id, videos in video_queues:
            if i < len(videos):
                merged.append((videos[i], pl_id))

    scheduled = []
    for k, (video_path, pl_id) in enumerate(merged):
        slot_idx = k % slots_per_day
        day_offset = k // slots_per_day
        current_date = start_date + timedelta(days=day_offset)
        slot_name, hour_start, hour_end = active_windows[slot_idx]

        if random_times:
            publish_at = random_time_in_window(current_date, hour_start, hour_end)
        else:
            publish_at = random_time_in_window(current_date, hour_start, hour_start + 1)

        pl_config = config_by_pl.get(pl_id, {})
        pl_captions = captions_by_pl.get(pl_id, [])

        if caption_mode == "random" and pl_captions:
            caption = random.choice(pl_captions)
        elif caption_mode == "fixed":
            caption = fixed_caption
        else:
            caption = ""

        # ── Hashtags: core always + N random from pool (if enabled) ──
        if pl_config.get("hashtagsEnabled", True):
            core_ht = [h.strip() for h in pl_config.get("hashtagsCore", pl_config.get("hashtags", "")).split(",") if h.strip()]
            pool_ht = [h.strip() for h in pl_config.get("hashtagsPool", "").split(",") if h.strip()]
            pick_ht = int(pl_config.get("hashtagsPickN", 3))
            picked_ht = random.sample(pool_ht, min(pick_ht, len(pool_ht))) if pool_ht else []
            final_hashtags = core_ht + picked_ht
        else:
            final_hashtags = []

        # ── Tags: core always + N random from pool (if enabled) ──
        if pl_config.get("tagsEnabled", True):
            core_tg = [t.strip() for t in pl_config.get("tagsCore", pl_config.get("tags", "")).split(",") if t.strip()]
            pool_tg = [t.strip() for t in pl_config.get("tagsPool", "").split(",") if t.strip()]
            pick_tg = int(pl_config.get("tagsPickN", 5))
            picked_tg = random.sample(pool_tg, min(pick_tg, len(pool_tg))) if pool_tg else []
            final_tags = core_tg + picked_tg
        else:
            final_tags = []

        meta = {
            "title": caption,
            "description": "",  # build_description adds hashtags only
            "tags": final_tags,
            "hashtags": final_hashtags,
            "privacy": privacy,
            "madeForKids": made_for_kids,
            "language": pl_config.get("language", "en"),
            "categoryId": pl_config.get("category", "auto"),
            "publishAt": publish_at,
        }

        meta_path = os.path.splitext(video_path)[0] + ".json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        scheduled.append({
            "video": os.path.basename(video_path),
            "playlist": pl_id,
            "playlistDisplay": pl_config.get("displayName", pl_id),
            "date": str(current_date),
            "slot": slot_name,
            "publishAt": publish_at,
            "caption": caption,
        })

    return jsonify({"scheduled": scheduled, "account": account})


@app.route("/start-upload", methods=["POST"])
def start_upload():
    global upload_log, upload_running
    data = request.json
    account = data.get("account")
    playlists = data.get("playlists", [])
    if not playlists:
        pl = data.get("playlist")
        if pl:
            playlists = [pl]

    if upload_running:
        return jsonify({"error": "Upload already running"}), 400

    upload_log = []
    upload_running = True

    def run():
        global upload_running
        try:
            venv_python = os.path.join("venv", "bin", "python3")
            python = venv_python if os.path.exists(venv_python) else "python3"
            for pl in playlists:
                videos_folder = os.path.join(playlist_path(pl), "videos")
                upload_log.append(f"▶ Uploading subtopic: {pl}")
                proc = subprocess.Popen(
                    [python, "upload.py", "--account", account, "--videos-folder", videos_folder],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                for line in proc.stdout:
                    upload_log.append(line.rstrip())
                proc.wait()
                upload_log.append(f"✓ Done: {pl}")
        except Exception as e:
            upload_log.append(f"Error: {e}")
        finally:
            upload_running = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/upload-status")
def upload_status():
    return jsonify({"log": upload_log, "running": upload_running})


@app.route("/delete-video/<playlist>", methods=["POST"])
def delete_video(playlist):
    data = request.json
    filename = secure_filename(data.get("filename", ""))
    folder = os.path.join(playlist_path(playlist), "videos")
    video_path = os.path.join(folder, filename)
    json_path = os.path.splitext(video_path)[0] + ".json"
    if os.path.exists(video_path):
        os.remove(video_path)
    if os.path.exists(json_path):
        os.remove(json_path)
    return jsonify({"ok": True})


if __name__ == "__main__":
    os.makedirs(PLAYLISTS_FOLDER, exist_ok=True)
    app.run(debug=True, port=5001)
