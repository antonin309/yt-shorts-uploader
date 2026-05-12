import os
import json
import glob
import random
import threading
import subprocess
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024

ACCOUNTS_FOLDER = "accounts"
PLAYLISTS_FOLDER = "playlists"

TIME_WINDOWS = [
    ("Früh", 6, 8),
    ("Vormittags", 8, 11),
    ("Mittag", 11, 13),
    ("Nachmittags", 13, 16),
    ("Abends", 18, 20),
    ("Spätabends", 21, 23),
]

upload_log = []
upload_running = False


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
    files = sorted(glob.glob(os.path.join(folder, "*.mp4")))
    return [os.path.basename(f) for f in files]


def random_time_in_window(date, hour_start, hour_end):
    hour = random.randint(hour_start, hour_end - 1)
    minute = random.randint(0, 59)
    local_dt = datetime(date.year, date.month, date.day, hour, minute,
                        tzinfo=timezone(timedelta(hours=2)))
    utc_dt = local_dt.astimezone(timezone.utc)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


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
        return jsonify({"error": "Keine Datei"}), 400
    files = request.files.getlist("videos")
    uploaded = []
    for f in files:
        if f.filename.endswith(".mp4"):
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


@app.route("/create-account", methods=["POST"])
def create_account():
    data = request.json
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Kein Name"}), 400
    os.makedirs(os.path.join(ACCOUNTS_FOLDER, name), exist_ok=True)
    return jsonify({"ok": True, "name": name})


@app.route("/create-playlist", methods=["POST"])
def create_playlist():
    data = request.json
    name = data.get("name", "").strip().lower().replace(" ", "-")
    if not name:
        return jsonify({"error": "Kein Name"}), 400
    folder = playlist_path(name)
    os.makedirs(os.path.join(folder, "videos"), exist_ok=True)
    config = {
        "account": data.get("account", ""),
        "displayName": data.get("displayName", name),
        "hashtags": data.get("hashtags", "#Shorts"),
        "tags": data.get("tags", ""),
        "privacy": "public",
        "language": "en"
    }
    with open(os.path.join(folder, "config.json"), "w") as f:
        json.dump(config, f, indent=2)
    with open(os.path.join(folder, "captions.txt"), "w") as f:
        f.write("")
    return jsonify({"ok": True, "name": name})


@app.route("/schedule", methods=["POST"])
def schedule():
    data = request.json
    playlist = data.get("playlist")
    account = data.get("account")
    start_date_str = data.get("startDate")
    hashtags = [h.strip() for h in data.get("hashtags", "#Shorts").split(",")]
    tags = [t.strip() for t in data.get("tags", "").split(",") if t.strip()]
    privacy = data.get("privacy", "public")
    caption_mode = data.get("captionMode", "random")
    fixed_caption = data.get("fixedCaption", "")
    random_times = data.get("randomTimes", True)
    active_slots = data.get("activeSlots", [1, 3, 4, 5])
    captions = load_playlist_captions(playlist)

    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    videos_folder = os.path.join(playlist_path(playlist), "videos")
    video_files = sorted(glob.glob(os.path.join(videos_folder, "*.mp4")))

    active_windows = [TIME_WINDOWS[i] for i in active_slots if i < len(TIME_WINDOWS)]
    if not active_windows:
        active_windows = TIME_WINDOWS

    scheduled = []
    for i, video_path in enumerate(video_files):
        slot_idx = i % len(active_windows)
        day_offset = i // len(active_windows)
        current_date = start_date + timedelta(days=day_offset)
        slot_name, hour_start, hour_end = active_windows[slot_idx]
        if random_times:
            publish_at = random_time_in_window(current_date, hour_start, hour_end)
        else:
            publish_at = random_time_in_window(current_date, hour_start, hour_start + 1)

        if caption_mode == "random" and captions:
            caption = random.choice(captions)
        elif caption_mode == "fixed":
            caption = fixed_caption
        else:
            caption = ""

        meta = {
            "title": caption,
            "description": caption,
            "tags": tags,
            "hashtags": hashtags,
            "privacy": privacy,
            "madeForKids": False,
            "language": "en",
            "publishAt": publish_at,
        }

        meta_path = os.path.splitext(video_path)[0] + ".json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        scheduled.append({
            "video": os.path.basename(video_path),
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
    playlist = data.get("playlist")

    if upload_running:
        return jsonify({"error": "Upload läuft bereits"}), 400

    videos_folder = os.path.join(playlist_path(playlist), "videos")
    upload_log = []
    upload_running = True

    def run():
        global upload_running
        try:
            venv_python = os.path.join("venv", "bin", "python3")
            python = venv_python if os.path.exists(venv_python) else "python3"
            proc = subprocess.Popen(
                [python, "upload.py", "--account", account, "--videos-folder", videos_folder],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            for line in proc.stdout:
                upload_log.append(line.rstrip())
            proc.wait()
        except Exception as e:
            upload_log.append(f"Fehler: {e}")
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
    json_path = video_path.replace(".mp4", ".json")
    if os.path.exists(video_path):
        os.remove(video_path)
    if os.path.exists(json_path):
        os.remove(json_path)
    return jsonify({"ok": True})


if __name__ == "__main__":
    os.makedirs(PLAYLISTS_FOLDER, exist_ok=True)
    app.run(debug=True, port=5001)
