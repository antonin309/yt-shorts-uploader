import os
import json
import glob
import argparse
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.http
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_FILE = "client.json"
VIDEOS_FOLDER = "videos"
ACCOUNTS_FOLDER = "accounts"


def authenticate(account):
    token_path = os.path.join(ACCOUNTS_FOLDER, account, "token.json")
    os.makedirs(os.path.dirname(token_path), exist_ok=True)

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                CLIENT_FILE, SCOPES
            )
            print(f"\nLogin für Account: {account}")
            creds = flow.run_local_server(port=0)

        with open(token_path, "w") as f:
            f.write(creds.to_json())
        print(f"Token gespeichert für: {account}\n")

    return googleapiclient.discovery.build("youtube", "v3", credentials=creds)


def build_description(meta):
    description = meta.get("description", "")
    hashtags = meta.get("hashtags", [])

    if hashtags:
        description = description.rstrip() + "\n\n" + " ".join(hashtags)

    if "#Shorts" not in description:
        description = description.rstrip() + "\n\n#Shorts"

    return description


def upload_video(youtube, video_path, meta_path):
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    title = meta.get("title", "")
    description = build_description(meta)
    tags = meta.get("tags", [])
    if "Shorts" not in tags:
        tags.append("Shorts")
    privacy = meta.get("privacy", "public")
    made_for_kids = meta.get("madeForKids", False)
    publish_at = meta.get("publishAt", None)
    language = meta.get("language", "de")

    status = {
        "privacyStatus": "private" if publish_at else privacy,
        "madeForKids": made_for_kids,
        "selfDeclaredMadeForKids": made_for_kids,
    }
    if publish_at:
        status["publishAt"] = publish_at

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "22",
            "defaultLanguage": language,
        },
        "status": status,
    }

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=googleapiclient.http.MediaFileUpload(
            video_path, chunksize=-1, resumable=True
        ),
    )

    print(f"Uploading: {os.path.basename(video_path)}")
    response = None
    while response is None:
        status_obj, response = request.next_chunk()
        if status_obj:
            print(f"  {int(status_obj.progress() * 100)}%")

    video_id = response["id"]
    print(f"  Fertig! https://youtube.com/shorts/{video_id}")
    if publish_at:
        print(f"  Geplant für: {publish_at}")
    return video_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", required=True, help="Account-Name (z.B. sunset-vibes)")
    parser.add_argument("--videos-folder", default=VIDEOS_FOLDER, help="Pfad zum Videos-Ordner")
    args = parser.parse_args()

    youtube = authenticate(args.account)

    video_files = sorted(glob.glob(os.path.join(args.videos_folder, "*.mp4")))

    if not video_files:
        print(f"Keine Videos in '{VIDEOS_FOLDER}/' gefunden.")
        return

    uploaded = 0
    for video_path in video_files:
        meta_path = video_path.replace(".mp4", ".json")
        if not os.path.exists(meta_path):
            print(f"Übersprungen (keine .json): {os.path.basename(video_path)}")
            continue
        upload_video(youtube, video_path, meta_path)
        uploaded += 1

    print(f"\n{uploaded} Video(s) hochgeladen auf '{args.account}' aus '{args.videos_folder}'.")


if __name__ == "__main__":
    main()
