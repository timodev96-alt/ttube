import imageio_ffmpeg
import argparse
import sys
from yt_dlp import YoutubeDL



def progress_hook(d):
    if d["status"] == "downloading":
        percent = d.get("_percent_str", "0.0%").strip()
        speed = d.get("_speed_str", "?").strip()
        eta = d.get("_eta_str", "?").strip()
        sys.stdout.write(f"\r  {percent}  |  {speed}  |  ETA {eta}   ")
        sys.stdout.flush()
    elif d["status"] == "finished":
        sys.stdout.write("\r" + " " * 60 + "\r")
        print("  Downloaded. Finalizing...")

def height_from_resolution(resolution):
    try:
        return int(resolution.split("x")[-1])
    except (ValueError, AttributeError):
        return 0

def get_available_formats(url, verbose=False):
    ydl_opts = {"quiet": not verbose, "no_warnings": not verbose}
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

def prompt_user_choice(options, label, output_format):
    if not options:
        print(f"No {label} formats available.")
        sys.exit(1)
    print(f"\n{label}  choose a quality: \n")
    for idx, opt in enumerate(options, 1):
        if "abr" in opt:
            desc = f"{int(opt['abr'])} kbps (Audio)"
        else:
            res = opt['resolution']
            if "x" in res:
                height = res.split("x")[-1]
                quality_label = f"{height}p"
            else:
                quality_label = res

            fps = opt.get("fps")
            if fps and fps > 30:
                quality_label += str(int(fps))

            desc = f"{quality_label}"
            if opt.get("fps") and fps <= 30:
                desc += f" ({opt['fps']}fps)"

        print(f"  [{idx}]   {desc:<18}")

    while True:
        raw = input(f"\n  Select (1-{len(options)}): ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print("  Invalid choice, try again.")

def build_ydl_opts(format_spec, output_dir, as_mp3=False, verbose=False):
    ydl_opts = {
        "format": format_spec,
        "progress_hooks": [progress_hook],
        "outtmpl": f"{output_dir}/%(title)s.%(ext)s",
        "quiet": not verbose,
        "no_warnings": not verbose,
        "noprogress": True,
        "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe()
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

def download(url, format_spec, output_dir, as_mp3=False, verbose=False):
    ydl_opts = build_ydl_opts(format_spec, output_dir, as_mp3, verbose)
    print("\nDownloading:")
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    print("  Done!")


def main():
    parser = argparse.ArgumentParser(description="Simple YouTube downloading CLI app!")
    parser.add_argument("url", nargs="?",help="YouTube video URL")
    parser.add_argument("-o", "--output", default=".", help="Output directory (default: current folder)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show yt-dlp's raw output (for debugging)")
    args = parser.parse_args()

    if not args.url:
        print("=" * 60)
        print(" ttube - Youtube Video/Audio downloader!")
        print("="*60)
        print("\n Paste Youtube URL to get started!")
        print("   ttube <video_URL>")
        print("\n options:")
        print(" -o, --output Choose a download folder (Default current folder)")

    print("Fetching info...")
    title, duration, video_only, audio_only = get_available_formats(args.url, verbose=args.verbose)
    print_header(title, duration)

    print("\nWhat do you want to download?")
    print("  [1] Full Video")
    print("  [2] Audio only")

    while True:
        choice = input("\nChoose: ").strip()
        if choice in ["1", "2"]:
            break
        print("Invalid selection.")

    if choice == "1":
        picked = prompt_user_choice(video_only, "Video", "mp4")
        format_spec = f"{picked['format_id']}+bestaudio[ext=m4a]/bestaudio/best"
        download(args.url, format_spec, args.output, verbose=args.verbose)
    else:
        picked = prompt_user_choice(audio_only, "Audio", "mp3")
        download(args.url, picked["format_id"], args.output, as_mp3=True, verbose=args.verbose)

if __name__ == "__main__":
    main()