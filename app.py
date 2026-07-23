import argparse
import sys
from yt_dlp import YoutubeDL


def progress_hook(d):
    if d["status"] == "downloading":
        percent = d.get("_percent_str", "0.0%").strip()
        speed = d.get("_speed_str", "?").strip()
        eta = d.get("_eta_str", "?").strip()
        sys.stdout.write(f"\r[Downloading] {percent}, Speed: {speed}, ETA: {eta}")
        sys.stdout.flush()
    elif d["status"] == "finished":
        print("\nDownload complete! Processing...")


def height_from_resolution(resolution):
    try:
        return int(resolution.split("x")[-1])
    except (ValueError, AttributeError):
        return 0


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
    duration = info.get("duration_string", "?")

    video_only = {}
    audio_only = []

    for f in formats:
        if not f.get("url"):
            continue

        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        ext = f.get("ext", "")
        resolution = f.get("resolution") or f.get("format_note", "unknown")
        tbr = f.get("tbr") or 0

        if vcodec != "none" and acodec == "none":
            existing = video_only.get(resolution)
            if not existing or tbr > existing["tbr"]:
                video_only[resolution] = {
                    "format_id": f["format_id"],
                    "resolution": resolution,
                    "ext": ext,
                    "tbr": tbr,
                    "fps": f.get("fps"),
                }
        elif vcodec == "none" and acodec != "none":
            abr = f.get("abr", 0) or 0
            audio_only.append({"format_id": f["format_id"], "abr": abr, "ext": ext})

    video_only_list = sorted(video_only.values(), key=lambda x: height_from_resolution(x["resolution"]), reverse=True)
    audio_only_sorted = sorted(audio_only, key=lambda x: x["abr"], reverse=True)

    return title, duration, video_only_list, audio_only_sorted


def print_header(title, duration):
    print()
    print("=" * 60)
    print(f"{title}")
    print(f"Duration: {duration}")
    print("=" * 60)


def prompt_user_choice(options, label):
    if not options:
        print(f"No {label} formats available.")
        sys.exit(1)
    print(f"\n{label} — choose a quality:\n")
    for idx, opt in enumerate(options, 1):
        if "abr" in opt:
            desc = f"{int(opt['abr'])} kbps"
        else:
            fps = f" {opt['fps']}fps" if opt.get("fps") else ""
            desc = f"{opt['resolution']}{fps}"
        print(f"  [{idx}]  {desc:<18} ({opt['ext']})")

    while True:
        raw = input(f"\n  Select (1-{len(options)}): ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("  Invalid choice, try again.")


def build_ydl_opts(format_spec, output_dir, as_mp3=False):
    ydl_opts = {
        "format": format_spec,
        "progress_hooks": [progress_hook],
        "outtmpl": f"{output_dir}/%(title)s.%(ext)s",
    }
    if as_mp3:
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    else:
        ydl_opts["merge_output_format"] = "mp4"
    return ydl_opts


def download(url, format_spec, output_dir, as_mp3=False):
    ydl_opts = build_ydl_opts(format_spec, output_dir, as_mp3)
    print("\nDownloading...")
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    print("\nDone!")


def main():
    parser = argparse.ArgumentParser(description="Simple YouTube downloading CLI app!")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("-o", "--output", default=".", help="Output directory (default: current folder)")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress yt-dlp's own log output")
    args = parser.parse_args()

    print("Fetching info...")
    title, duration, video_only, audio_only = get_available_formats(args.url, quiet=args.quiet)
    print_header(title, duration)

    print("\nWhat do you want to download?")
    print("  [1] Video")
    print("  [2] Audio only")

    while True:
        choice = input("\nChoose: ").strip()
        if choice in ["1", "2"]:
            break
        print("Invalid selection.")

    if choice == "1":
        picked = prompt_user_choice(video_only, "Video")
        format_spec = f"{picked['format_id']}+bestaudio/best"
        download(args.url, format_spec, args.output)
    else:
        picked = prompt_user_choice(audio_only, "Audio")
        download(args.url, picked["format_id"], args.output, as_mp3=True)


if __name__ == "__main__":
    main()