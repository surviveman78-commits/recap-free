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
        ydl_opts = {
            'format': 'bestvideo*+bestaudio/best',
            'format_sort': ['res:2160', 'res', 'fps', 'quality', 'size', 'br'],
            'outtmpl': out_template,
            'merge_output_format': 'mp4',
            'progress_hooks': [self._hook],
            'noplaylist': True,
            'socket_timeout': 30,
            'retries': 10,
            'fragment_retries': 10,
            'http_chunk_size': 10485760,
            'extractor_args': {'youtube': {'player_client': ['web', 'tv_embedded', 'android']}},
            'quiet': True,
            'no_warnings': True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

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
