import argparse
import sys
from yt_dlp import YoutubeDL


def progress_hook(d):
    if d["status"] == "downloading":
        percent = d.get("_percent_str", "0.0%").strip()
        speed = d.get("_speed_str", "Unknown speed").strip()
        eta = d.get("_eta_str", "Unknown ETA").strip()
        sys.stdout.write(f"\r[Downloading] {percent}, Speed: {speed}, ETA: {eta}")
        sys.stdout.flush()
    elif d["status"] == "finished":
        print("\nDownload complete! Processing...")


def get_available_formats(url, quiet=True):
    ydl_opts = {"quiet": quiet, "no_warnings": quiet}
    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            print(f"Error fetching video info: {e}")
            sys.exit(1)

    formats = info.get("formats", [])
    title = info.get("title", "Unknown Title")

    video_only = []
    audio_only = []
    full_video = []

    for f in formats:
        if not f.get("url"):
            continue

        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        ext = f.get("ext", "")
        resolution = f.get("resolution") or f.get("format_note", "unknown")

        if vcodec != "none" and acodec == "none":
            video_only.append({"format_id": f["format_id"], "resolution": resolution, "ext": ext})
        elif vcodec == "none" and acodec != "none":
            abr = f.get("abr", "unknown")
            audio_only.append({"format_id": f["format_id"], "abr": abr, "ext": ext})
        elif vcodec != "none" and acodec != "none":
            full_video.append({"format_id": f["format_id"], "resolution": resolution, "ext": ext})

    # return AFTER the loop finishes, not inside it
    return title, full_video, video_only, audio_only


def prompt_user_choice(options, label_key):
    if not options:
        print(f"No {label_key} formats available.")
        sys.exit(1)
    print(f"\nAvailable {label_key} options:")
    for idx, opt in enumerate(options, 1):
        desc = opt.get("resolution") or f"{opt.get('abr')} kbps"
        print(f"[{idx}] Quality: {desc} (format: {opt['ext']})")

    while True:
        try:
            choice = int(input(f"Select option (1-{len(options)}): "))
            if 1 <= choice <= len(options):
                return options[choice - 1]["format_id"]
        except ValueError:
            pass
        print("Invalid choice... please try again")


def build_ydl_opts(format_id, output_dir, as_mp3=False):
    ydl_opts = {
        "format": format_id,
        "progress_hooks": [progress_hook],
        "outtmpl": f"{output_dir}/%(title)s.%(ext)s",
    }
    if as_mp3:
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    return ydl_opts


def download(url, format_id, output_dir, as_mp3=False):
    ydl_opts = build_ydl_opts(format_id, output_dir, as_mp3)
    print("\nDownloading...")
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    print("\nDone!")


def main():
    parser = argparse.ArgumentParser(description="Simple YouTube downloading CLI app!")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("-o", "--output", default=".", help="Output directory (default: current folder)")
    parser.add_argument("-a", "--audio-only", action="store_true", help="Skip menu, download best audio as MP3")
    parser.add_argument("-b", "--best-video", action="store_true", help="Skip menu, download best full video")
    parser.add_argument("--list-formats", action="store_true", help="List available formats and exit")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress yt-dlp's own log output")
    args = parser.parse_args()

    print("Fetching info...")
    title, full_video, video_only, audio_only = get_available_formats(args.url, quiet=args.quiet)
    print(f"\nTitle: {title}")

    if args.list_formats:
        for label, opts in [("Full Video", full_video), ("Video Only", video_only), ("Audio Only", audio_only)]:
            print(f"\n--- {label} ---")
            for opt in opts:
                desc = opt.get("resolution") or f"{opt.get('abr')} kbps"
                print(f"  id={opt['format_id']:>6}  {desc}  ({opt['ext']})")
        return

    if args.audio_only:
        format_id = prompt_user_choice(audio_only, "Audio Only")
        download(args.url, format_id, args.output, as_mp3=True)
        return

    if args.best_video:
        format_id = prompt_user_choice(full_video, "Full Video")
        download(args.url, format_id, args.output)
        return

    print("\nChoose Download Type:")
    print(" [1] Full Video")
    print(" [2] Video Only")
    print(" [3] Audio Only")

    while True:
        choice = input("Choose: ").strip()
        if choice in ["1", "2", "3"]:
            break
        print("Invalid selection.")

    if choice == "1":
        format_id = prompt_user_choice(full_video, "Full Video")
        download(args.url, format_id, args.output)
    elif choice == "2":
        format_id = prompt_user_choice(video_only, "Video Only")
        download(args.url, format_id, args.output)
    elif choice == "3":
        format_id = prompt_user_choice(audio_only, "Audio Only")
        download(args.url, format_id, args.output, as_mp3=True)


if __name__ == "__main__":
    main()