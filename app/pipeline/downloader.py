import os
import re
from pathlib import Path
from typing import Callable, Optional
import yt_dlp

class VideoDownloader:
    def __init__(self, output_dir: Path, progress_callback: Optional[Callable[[str, float], None]] = None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.progress_callback = progress_callback
        self.downloaded_file: Optional[Path] = None

    def _hook(self, d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            percent = 0.0
            if total > 0:
                percent = round((downloaded / total) * 100, 1)
            elif '_percent_str' in d:
                cleaned = re.sub(r'[^\d.]', '', d['_percent_str'])
                try:
                    percent = float(cleaned)
                except ValueError:
                    percent = 50.0
            speed = d.get('_speed_str', '')
            eta = d.get('_eta_str', '')
            msg = f"Downloading... {percent}%"
            if speed:
                msg += f" ({speed})"
            if eta:
                msg += f" ETA {eta}"
            if self.progress_callback:
                self.progress_callback(msg, percent)
        elif d['status'] == 'finished':
            if self.progress_callback:
                self.progress_callback("Download finished, finalizing media...", 100.0)

    def download(self, url: str) -> Path:
        out_template = str(self.output_dir / "downloaded_video.%(ext)s")
        cookie_candidates = [
            Path(os.getenv("YTDLP_COOKIES", "")) if os.getenv("YTDLP_COOKIES") else None,
            self.output_dir.parent.parent / "youtube_cookies.txt",
            Path("/kaggle/working/youtube_cookies.txt"),
        ]
        kaggle_input = Path("/kaggle/input")
        if kaggle_input.exists():
            cookie_candidates.extend(sorted(kaggle_input.rglob("youtube_cookies.txt")))
        cookie_file = next((p for p in cookie_candidates if p and p.exists()), None)
        ydl_opts = {
            'format': 'bv*+ba/b',
            'format_sort': ['res:2160', 'res', 'fps', 'quality', 'size', 'br'],
            'outtmpl': out_template,
            'merge_output_format': 'mp4',
            'progress_hooks': [self._hook],
            'noplaylist': True,
            'socket_timeout': 30,
            'retries': 10,
            'fragment_retries': 10,
            'http_chunk_size': 10485760,
            'quiet': True,
            'no_warnings': True
        }
        if cookie_file:
            ydl_opts['cookiefile'] = str(cookie_file)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except yt_dlp.utils.DownloadError as exc:
            message = str(exc)
            if "not a bot" in message.lower() or "sign in" in message.lower() or "confirm" in message.lower():
                raise RuntimeError(
                    "YouTube က Kaggle IP ကို anti-bot ဖြင့်ပိတ်ထားပါသည်။ "
                    "အခြား public video တစ်ခု စမ်းပါ၊ local video upload လုပ်ပါ၊ "
                    "သို့မဟုတ် ကိုယ်ပိုင် YouTube cookies file ကို youtube_cookies.txt အဖြစ် "
                    "Kaggle Input ထဲထည့်ပြီး server မစခင် /kaggle/working/youtube_cookies.txt သို့ copy လုပ်ပါ။"
                ) from exc
            raise RuntimeError(f"Video download failed: {message[:500]}") from exc

        # Locate resulting video
        candidates = list(self.output_dir.glob("downloaded_video.*"))
        if not candidates:
            # Check any video in folder
            candidates = [p for p in self.output_dir.glob("*") if p.suffix.lower() in ('.mp4', '.mkv', '.webm', '.mov')]

        if not candidates:
            raise FileNotFoundError(f"Failed to find downloaded video in {self.output_dir}")

        # If merged or preferred mp4 exists, pick it
        mp4_candidates = [p for p in candidates if p.suffix.lower() == '.mp4']
        self.downloaded_file = mp4_candidates[0] if mp4_candidates else candidates[0]
        return self.downloaded_file
