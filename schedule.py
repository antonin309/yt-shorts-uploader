import os
import json
import glob
import argparse
import random
from datetime import datetime, timedelta, timezone

VIDEOS_FOLDER = "videos"

# Zeitfenster in DE Sommerzeit (UTC+2), wird automatisch umgerechnet
TIME_WINDOWS = [
    (8, 11),    # Vormittags
    (13, 15),   # Nachmittags
    (18, 20),   # Abends
    (21, 23),   # Spätabends
]


def random_time_in_window(date, hour_start, hour_end):
    hour = random.randint(hour_start, hour_end - 1)
    minute = random.randint(0, 59)
    # DE Sommerzeit = UTC+2
    local_dt = datetime(date.year, date.month, date.day, hour, minute, tzinfo=timezone(timedelta(hours=2)))
    utc_dt = local_dt.astimezone(timezone.utc)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="Startdatum (YYYY-MM-DD)")
    parser.add_argument("--title-prefix", default="", help="Titel-Prefix für alle Videos")
    parser.add_argument("--description", default="", help="Beschreibung für alle Videos")
    parser.add_argument("--hashtags", default="#Shorts", help="Hashtags kommagetrennt")
    parser.add_argument("--tags", default="", help="Tags kommagetrennt")
    parser.add_argument("--privacy", default="public", help="public oder private")
    parser.add_argument("--language", default="de")
    args = parser.parse_args()

    video_files = sorted(glob.glob(os.path.join(VIDEOS_FOLDER, "*.mp4")))

    if not video_files:
        print(f"Keine Videos in '{VIDEOS_FOLDER}/' gefunden.")
        return

    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    hashtags = [h.strip() for h in args.hashtags.split(",")]
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else []

    print(f"\n{len(video_files)} Videos gefunden — Schedule wird erstellt:\n")

    for i, video_path in enumerate(video_files):
        day_offset = i // 4
        slot = i % 4
        current_date = start_date + timedelta(days=day_offset)
        hour_start, hour_end = TIME_WINDOWS[slot]
        publish_at = random_time_in_window(current_date, hour_start, hour_end)

        slot_names = ["Vormittags", "Nachmittags", "Abends", "Spätabends"]
        base_name = os.path.splitext(video_path)[0]
        meta_path = base_name + ".json"

        title = args.title_prefix if args.title_prefix else os.path.basename(base_name)

        meta = {
            "title": title,
            "description": args.description,
            "tags": tags,
            "hashtags": hashtags,
            "privacy": args.privacy,
            "madeForKids": False,
            "language": args.language,
            "publishAt": publish_at,
        }

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        print(f"  {os.path.basename(video_path)} → {current_date} {slot_names[slot]} ({publish_at})")

    print(f"\nFertig! Jetzt uploaden mit:")
    print(f"  python3 upload.py --account DEIN-ACCOUNT\n")


if __name__ == "__main__":
    main()
