import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import imageio_ffmpeg
from yt_dlp import YoutubeDL

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import (
    Progress, TextColumn, BarColumn, DownloadColumn,
    TransferSpeedColumn, TimeRemainingColumn,
)
from rich.prompt import Prompt, Confirm
from rich import box

console = Console()

CONFIG_DIR = Path.home() / ".ttube"
CONFIG_PATH = CONFIG_DIR / "config.json"
HISTORY_PATH = CONFIG_DIR / "history.json"

DEFAULT_CONFIG = {
    "output": ".",
    "default_type": None,   # "video" | "audio" | None (always ask)
}

BANNER = r"""
  _   _         _
 | |_| |_ _   _| |__   ___
 | __| __| | | | '_ \ / _ \
 | |_| |_| |_| | |_) |  __/
  \__|\__|\__,_|_.__/ \___|
"""


# ---------- config & history helpers ----------

def load_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path, data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_config():
    config = dict(DEFAULT_CONFIG)
    config.update(load_json(CONFIG_PATH, {}))
    return config


def load_history():
    return load_json(HISTORY_PATH, [])


def add_history_entry(entry):
    history = load_history()
    history.append(entry)
    save_json(HISTORY_PATH, history)


def find_previous_download(history, video_id):
    for entry in reversed(history):
        if entry.get("video_id") == video_id:
            return entry
    return None


# ---------- yt-dlp plumbing ----------

def make_progress_hook(progress, task_id):
    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                progress.update(task_id, total=total, completed=downloaded)
        elif d["status"] == "finished":
            progress.update(task_id, completed=progress.tasks[task_id].total or 0)
    return hook


def height_from_resolution(resolution):
    try:
        return int(resolution.split("x")[-1])
    except (ValueError, AttributeError):
        return 0


def get_available_formats(url, verbose=False):
    ydl_opts = {"quiet": not verbose, "no_warnings": not verbose}
    with console.status("[cyan]Fetching info...", spinner="dots"):
        with YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
            except Exception as e:
                console.print(f"[bold red]Error fetching info:[/bold red] {e}")
                sys.exit(1)

    formats = info.get("formats") or []
    title = info.get("title") or info.get("id") or "Unknown Title"
    duration = info.get("duration_string") or "?"
    media_id = info.get("id", "") or url
    site = info.get("extractor_key") or info.get("extractor") or "Unknown site"

    video_only = {}
    audio_only = []
    combined = {}   # sites that only offer video+audio already together (no separate streams)

    # Fallback: some extractors return a single direct 'url' with no 'formats' list at all
    if not formats and info.get("url"):
        formats = [{
            "format_id": info.get("format_id", "0"),
            "url": info["url"],
            "ext": info.get("ext", "mp4"),
            "vcodec": info.get("vcodec", "unknown"),
            "acodec": info.get("acodec", "unknown"),
            "resolution": info.get("resolution", "unknown"),
            "tbr": info.get("tbr", 0),
            "fps": info.get("fps"),
        }]

    for f in formats:
        if not f.get("url"):
            continue

        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        ext = f.get("ext", "")
        resolution = f.get("resolution") or f.get("format_note") or "unknown"
        tbr = f.get("tbr") or 0

        is_video = vcodec not in ("none", None)
        is_audio = acodec not in ("none", None)

        if is_video and not is_audio:
            existing = video_only.get(resolution)
            if not existing or tbr > existing["tbr"]:
                video_only[resolution] = {
                    "format_id": f["format_id"], "resolution": resolution,
                    "ext": ext, "tbr": tbr, "fps": f.get("fps"),
                }
        elif is_audio and not is_video:
            abr = f.get("abr", 0) or 0
            audio_only.append({"format_id": f["format_id"], "abr": abr, "ext": ext})
        elif is_video and is_audio:
            existing = combined.get(resolution)
            if not existing or tbr > existing["tbr"]:
                combined[resolution] = {
                    "format_id": f["format_id"], "resolution": resolution,
                    "ext": ext, "tbr": tbr, "fps": f.get("fps"),
                }

    video_only_list = sorted(video_only.values(), key=lambda x: height_from_resolution(x["resolution"]), reverse=True)
    audio_only_sorted = sorted(audio_only, key=lambda x: x["abr"], reverse=True)
    combined_list = sorted(combined.values(), key=lambda x: height_from_resolution(x["resolution"]), reverse=True)

    return {
        "title": title,
        "duration": duration,
        "media_id": media_id,
        "site": site,
        "video_only": video_only_list,
        "audio_only": audio_only_sorted,
        "combined": combined_list,
    }


def print_header(title, duration, site):
    console.print()
    console.print(Panel(
        f"[bold white]{title}[/bold white]\n[dim]{site} · Duration: {duration}[/dim]",
        border_style="magenta",
        box=box.ROUNDED,
    ))


def prompt_user_choice(options, label, output_format):
    if not options:
        console.print(f"[red]No {label} formats available.[/red]")
        sys.exit(1)

    table = Table(title=f"{label} — choose a quality (saved as .{output_format})", box=box.SIMPLE_HEAVY, header_style="bold cyan")
    table.add_column("#", justify="right", style="bold yellow")
    table.add_column("Quality", style="white")

    for idx, opt in enumerate(options, 1):
        if "abr" in opt:
            desc = f"{int(opt['abr'])} kbps"
        else:
            res = opt["resolution"]
            if "x" in res:
                height = res.split("x")[-1]
                quality_label = f"{height}p"
            else:
                quality_label = res

            fps = opt.get("fps")
            if fps and fps > 30:
                quality_label += str(int(fps))
                desc = quality_label
            elif fps:
                desc = f"{quality_label} ({fps}fps)"
            else:
                desc = quality_label

        table.add_row(str(idx), desc)

    console.print(table)

    while True:
        raw = Prompt.ask(f"  Select [1-{len(options)}]").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        console.print("[red]Invalid choice, try again.[/red]")


def build_ydl_opts(format_spec, output_dir, progress_hook, as_mp3=False, verbose=False):
    ydl_opts = {
        "format": format_spec,
        "progress_hooks": [progress_hook],
        "outtmpl": f"{output_dir}/%(title)s.%(ext)s",
        "quiet": not verbose,
        "no_warnings": not verbose,
        "noprogress": True,
        "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
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
    console.print()
    with Progress(
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=None, complete_style="magenta", finished_style="green"),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task("Downloading", total=None)
        hook = make_progress_hook(progress, task_id)
        ydl_opts = build_ydl_opts(format_spec, output_dir, hook, as_mp3, verbose)
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

    console.print("[bold green]✔ Done![/bold green]")
    return info


# ---------- subcommands ----------

def cmd_config(args):
    config = load_config()

    if args.show or (not args.set_output and not args.set_type):
        table = Table(title="ttube config", box=box.SIMPLE_HEAVY, header_style="bold cyan")
        table.add_column("Setting", style="yellow")
        table.add_column("Value", style="white")
        for k, v in config.items():
            table.add_row(k, str(v))
        console.print(table)
        console.print(f"[dim]Stored at: {CONFIG_PATH}[/dim]")
        return

    if args.set_output:
        config["output"] = args.set_output
    if args.set_type:
        config["default_type"] = None if args.set_type == "ask" else args.set_type

    save_json(CONFIG_PATH, config)
    console.print("[bold green]Config updated:[/bold green]")
    for k, v in config.items():
        console.print(f"  [yellow]{k}[/yellow]: {v}")


def cmd_history(args):
    history = load_history()
    if not history:
        console.print("[dim]No downloads yet.[/dim]")
        return

    entries = history[-args.limit:] if args.limit else history
    table = Table(title=f"ttube history (showing {len(entries)} of {len(history)})", box=box.SIMPLE_HEAVY, header_style="bold cyan")
    table.add_column("Date", style="dim", width=17, no_wrap=True)
    table.add_column("Title", style="white", max_width=22, no_wrap=True, overflow="ellipsis")
    table.add_column("Type", style="magenta", width=6)
    table.add_column("Quality", style="yellow", width=9)
    table.add_column("File", style="dim", max_width=16, no_wrap=True, overflow="ellipsis")

    for entry in reversed(entries):
        table.add_row(entry["date"], entry["title"], entry["type"], entry.get("quality", "?"), entry["file_path"])

    console.print(table)


def cmd_download(args, config):
    result = get_available_formats(args.url, verbose=args.verbose)
    title = result["title"]
    print_header(title, result["duration"], result["site"])

    video_only = result["video_only"]
    audio_only = result["audio_only"]
    combined = result["combined"]

    history = load_history()
    previous = find_previous_download(history, result["media_id"])
    if previous:
        console.print(
            f"\n[yellow]Note:[/yellow] you already downloaded this on {previous['date']} "
            f"([bold]{previous['type']}[/bold], saved to {previous['file_path']})."
        )
        if not Confirm.ask("  Download again anyway?", default=False):
            console.print("[dim]Skipped.[/dim]")
            return

    has_video = bool(video_only) or bool(combined)
    has_audio = bool(audio_only)

    dl_type = config.get("default_type")
    if dl_type not in ("video", "audio"):
        if has_video and has_audio:
            console.print("\n[bold]What do you want to download?[/bold]")
            console.print("  [cyan][1][/cyan] Full Video")
            console.print("  [cyan][2][/cyan] Audio only")
            while True:
                choice = Prompt.ask("Choose").strip()
                if choice in ["1", "2"]:
                    break
                console.print("[red]Invalid selection.[/red]")
            dl_type = "video" if choice == "1" else "audio"
        elif has_video:
            dl_type = "video"
        elif has_audio:
            dl_type = "audio"
        else:
            console.print("[bold red]No downloadable video or audio streams found for this URL.[/bold red]")
            sys.exit(1)

    output_dir = args.output or config.get("output", ".")

    if dl_type == "video":
        if video_only:
            # YouTube-style: separate video-only streams, merge with best m4a audio
            picked = prompt_user_choice(video_only, "Video", "mp4")
            format_spec = f"{picked['format_id']}+bestaudio[ext=m4a]/bestaudio/best"
        else:
            # Combined-format site: video+audio already together, just grab it directly
            picked = prompt_user_choice(combined, "Video", "mp4")
            format_spec = picked["format_id"]
        download(args.url, format_spec, output_dir, verbose=args.verbose)
        quality_desc = picked["resolution"]
        ext = "mp4"
    else:
        picked = prompt_user_choice(audio_only, "Audio", "mp3")
        download(args.url, picked["format_id"], output_dir, as_mp3=True, verbose=args.verbose)
        quality_desc = f"{int(picked['abr'])}kbps"
        ext = "mp3"

    safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()
    file_path = str(Path(output_dir) / f"{safe_title}.{ext}")

    add_history_entry({
        "video_id": result["media_id"],
        "title": title,
        "url": args.url,
        "type": dl_type,
        "quality": quality_desc,
        "file_path": file_path,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })


# ---------- entry point ----------

def print_welcome():
    console.print(BANNER, style="bold magenta", highlight=False)
    console.print(Panel(
        "[bold]Paste a video/audio URL to get started:[/bold]\n\n"
        '  [cyan]ttube[/cyan] "https://www.youtube.com/watch?v=dQw4w9WgXcQ"\n'
        '  [cyan]ttube[/cyan] "https://twitter.com/user/status/12345"\n'
        '  [cyan]ttube[/cyan] "https://soundcloud.com/artist/track"\n\n'
        "[dim]Works with YouTube, Twitter/X, TikTok, SoundCloud, Vimeo, Twitch,\n"
        "Reddit, Instagram, and 1000+ other sites supported by yt-dlp.[/dim]\n\n"
        "[bold]Other commands:[/bold]\n"
        "  [cyan]ttube history[/cyan]                Show past downloads\n"
        "  [cyan]ttube config[/cyan]                 Show current config\n"
        "  [cyan]ttube config --set-output[/cyan] <folder>\n"
        "  [cyan]ttube config --set-type[/cyan] video|audio|ask\n\n"
        "[bold]Options:[/bold]\n"
        "  [yellow]-o, --output[/yellow]   Download folder (overrides config)\n"
        "  [yellow]-v, --verbose[/yellow]  Show detailed logs",
        title="[bold magenta]ttube[/bold magenta] — Universal Media Downloader",
        border_style="magenta",
        box=box.ROUNDED,
    ))


KNOWN_COMMANDS = {"download", "history", "config"}


def build_download_parser(prog="ttube"):
    parser = argparse.ArgumentParser(prog=prog, description="ttube — Universal Media Downloader (powered by yt-dlp)")
    parser.add_argument("url", nargs="?", help="Video/audio URL (YouTube, Twitter/X, TikTok, SoundCloud, Vimeo, and more)")
    parser.add_argument("-o", "--output", default=None, help="Output directory (overrides config)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show yt-dlp's raw output")
    return parser


def build_history_parser():
    parser = argparse.ArgumentParser(prog="ttube history", description="Show past downloads")
    parser.add_argument("-n", "--limit", type=int, default=10, help="Number of entries to show (default 10, 0 for all)")
    return parser


def build_config_parser():
    parser = argparse.ArgumentParser(prog="ttube config", description="View or edit your default settings")
    parser.add_argument("--show", action="store_true", help="Show current config")
    parser.add_argument("--set-output", help="Set default output folder")
    parser.add_argument("--set-type", choices=["video", "audio", "ask"], help="Set default download type")
    return parser


def main():
    argv = sys.argv[1:]
    first = argv[0] if argv else None

    if first == "history":
        args = build_history_parser().parse_args(argv[1:])
        cmd_history(args)
        return

    if first == "config":
        args = build_config_parser().parse_args(argv[1:])
        cmd_config(args)
        return

    if first == "download":
        args = build_download_parser().parse_args(argv[1:])
    else:
        args = build_download_parser().parse_args(argv)

    if not args.url:
        print_welcome()
        return

    config = load_config()
    cmd_download(args, config)


if __name__ == "__main__":
    main()