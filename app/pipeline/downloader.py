import os
import re
import json
import urllib.parse
from pathlib import Path
from typing import Callable, Optional
import requests
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

    @staticmethod
    def _is_xhs_url(url: str) -> bool:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        return host == "xhslink.com" or host.endswith(".xhslink.com") or host.endswith("xiaohongshu.com")

    @staticmethod
    def _resolve_xhs_url(url: str) -> str:
        """Resolve xhslink short URLs without passing the login wrapper to yt-dlp."""
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            allow_redirects=True,
            timeout=30,
        )
        final_url = response.url
        parsed = urllib.parse.urlparse(final_url)
        query = urllib.parse.parse_qs(parsed.query)
        redirect_path = query.get("redirectPath", [None])[0]
        if redirect_path:
            # xhslink currently redirects through /login?redirectPath=...;
            # the encoded value contains the usable note URL and its token.
            return urllib.parse.unquote(redirect_path)
        return final_url

    def _download_xhs_direct(self, url: str, output_path: Path) -> Path:
        """Fallback for XHS's current noteData state format."""
        canonical = self._resolve_xhs_url(url)
        if "/explore/" not in canonical and "/discovery/item/" not in canonical:
            raise RuntimeError("Rednote link က public Xiaohongshu note URL သို့ မပြောင်းနိုင်ပါ။")
        page = requests.get(
            canonical.replace("http://", "https://"),
            headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
                "Referer": "https://www.xiaohongshu.com/",
            },
            timeout=45,
        )
        page.raise_for_status()
        marker = "window.__INITIAL_STATE__="
        start = page.text.find(marker)
        if start < 0:
            raise RuntimeError("Rednote page မှ video data မတွေ့ပါ။ Public link သို့မဟုတ် login လိုသော link ဖြစ်နိုင်ပါသည်။")
        start += len(marker)
        end = page.text.find("</script>", start)
        raw_state = page.text[start:end if end >= 0 else None]
        try:
            from yt_dlp.utils import js_to_json
            state = json.loads(js_to_json(raw_state))
        except Exception as exc:
            raise RuntimeError(f"Rednote page data ကိုဖတ်မရပါ: {exc}") from exc

        note = (((state.get("noteData") or {}).get("data") or {}).get("noteData") or {})
        streams = (((note.get("video") or {}).get("media") or {}).get("stream") or {})
        stream_candidates = []
        for codec in ("h264", "h265"):
            for item in streams.get(codec) or []:
                urls = ([item["masterUrl"]] if item.get("masterUrl") else []) + (item.get("backupUrls") or [])
                for media_url in urls:
                    stream_candidates.append({
                        "url": media_url,
                        "height": int(item.get("height") or 0),
                        "width": int(item.get("width") or 0),
                        "bitrate": int(item.get("avgBitrate") or item.get("videoBitrate") or 0),
                        # Prefer H.264 only when resolution and bitrate tie.
                        "codec_priority": 1 if codec == "h264" else 0,
                    })
        if not stream_candidates:
            raise RuntimeError("Rednote note ထဲတွင် downloadable video stream မတွေ့ပါ။")
        # Highest actual source resolution first. If a note has a 1080p/2K/4K
        # stream, it is selected before lower streams; a 720p-only source is
        # kept at its native maximum because a downloader must not pretend an
        # upscale is true 1080p.
        stream_candidates.sort(
            key=lambda item: (item["height"], item["width"], item["bitrate"], item["codec_priority"]),
            reverse=True,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        last_error = ""
        for candidate in stream_candidates:
            media_url = candidate["url"]
            try:
                with requests.get(media_url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.xiaohongshu.com/"}, stream=True, timeout=60) as media:
                    media.raise_for_status()
                    with output_path.open("wb") as target:
                        for chunk in media.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                target.write(chunk)
                if output_path.is_file() and output_path.stat().st_size > 1024:
                    return output_path
            except Exception as exc:
                last_error = str(exc)
        raise RuntimeError(f"Rednote video stream ကို download မရပါ: {last_error}")

    def download(self, url: str) -> Path:
        out_template = str(self.output_dir / "downloaded_video.%(ext)s")
        if self._is_xhs_url(url):
            direct_path = self.output_dir / "downloaded_video.mp4"
            try:
                self.downloaded_file = self._download_xhs_direct(url, direct_path)
                if self.progress_callback:
                    self.progress_callback("Rednote download finished.", 100.0)
                return self.downloaded_file
            except Exception as exc:
                raise RuntimeError(f"Rednote video download failed: {exc}") from exc
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
            # Try the highest tier first; if that tier is unavailable, fall
            # back in order to 2K, then 1080p, then the best source available.
            # This keeps 1080p as the minimum target whenever the source has it.
            'format': (
                'bestvideo[height>=2160]+bestaudio/best[height>=2160]/'
                'bestvideo[height>=1440]+bestaudio/best[height>=1440]/'
                'bestvideo[height>=1080]+bestaudio/best[height>=1080]/'
                'bestvideo+bestaudio/best'
            ),
            'format_sort': ['res', 'fps', 'quality', 'size', 'br'],
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
