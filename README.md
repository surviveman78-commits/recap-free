# AI Video Dubbing & Subtitling Studio

An automated, end-to-end AI video dubbing and subtitling application built completely from scratch. It automates video downloading, audio extraction, Groq speech-to-text transcription, Gemini AI rewriting/translation, multi-engine text-to-speech synthesis (Microsoft Edge TTS & VoxCPM2 Voice Clone), audio mixing, and 9:16 safe-area subtitle burning using FFmpeg.

---

## Complete Workflow Pipeline

The processing workflow strictly follows the **8 designated stages**:

```
VIDEO URL / UPLOAD
       ↓
1. Downloading...               (yt-dlp)
       ↓
2. Extracting audio...          (FFmpeg -> original_audio.wav)
       ↓
3. Creating transcript...       (Groq API STT -> transcript.json & transcript.txt)
       ↓
4. Transcribing / Rewriting...  (Gemini API -> processed_transcript.txt with timestamps)
       ↓
5. Generating TTS...            (Edge TTS / VoxCPM2 -> tts_audio.wav synchronized)
       ↓
6. Mixing audio...              (FFmpeg -> dubbed_video.mp4)
       ↓
7. Burning subtitles...         (FFmpeg ASS/SRT styling -> final_video.mp4)
       ↓
8. Complete                     (Interactive player & downloads)
```

---

## Key Features

- **Strict 8-Stage Progress**: The frontend displays real-time progress for all 8 stages with animated indicators and timestamps.
- **Dedicated STT & Rewrite Separation**:
  - **Groq API**: Audio $\to$ `transcript.json` and `transcript.txt` with verbose timestamps.
  - **Gemini API**: Script rewrite, translation, or flow polishing $\to$ `processed_transcript.txt` without overwriting the original Groq transcript.
- **Dual TTS Engine**:
  - **Microsoft Edge TTS**: Fast, expressive neural voices across dozens of languages (including English, Burmese `my-MM-ThihaNeural` / `my-MM-NilarNeural`, Thai, Spanish, etc.).
  - **VoxCPM2 Voice Clone**: Local diffusion-autoregressive voice cloning powered by your RTX 3070 GPU, using reference voices from `C:\Users\Zimmimoo\VoxCPM\examples` or uploaded voice clips.
- **Audio Synchronization**: Preserves segment start/end timings, adjusts tempos if necessary, and pads silence so speech matches video pacing.
- **9:16 Safe Subtitle Burning**: Automatically adapts font size and vertical margins for portrait (TikTok/Reels/Shorts) and widescreen formats with crisp white text and dark outlines.
- **API Key Security**:
  - Masked password inputs in the UI Settings panel.
  - API keys are never hardcoded, never logged, never exposed in client JS, and excluded via `.gitignore`.
  - Keys are saved locally in `config/settings.json` (git-ignored).

---

## Quick Start

### 1. Launch the Application

Simply double-click `run.bat` or run:

```bash
python run.py
```

The application will start at `http://127.0.0.1:8000` and automatically open your default browser.

### 2. Enter API Keys

1. Click **Settings** in the top right.
2. Enter your **Groq API Key** and **Gemini API Key**.
3. Choose your default voice engine (**Microsoft Edge TTS** or **VoxCPM2**).
4. Click **Save Settings**.

### 3. Start Dubbing

1. Paste a video URL (YouTube, TikTok, Shorts, Twitter, etc.) or choose **Upload Local Video**.
2. Select your Gemini Processing Mode (Rewrite, Burmese translation, English translation, or Dynamic dub).
3. Click **Start Pipeline**.
4. Watch the 8-stage progress, view the side-by-side transcripts, and preview/download your final dubbed video.

---

## Kaggle Notebook (recommended)

The repository now includes [`RECAP_FREE_Kaggle.ipynb`](RECAP_FREE_Kaggle.ipynb), which is the supported Kaggle workflow. In Kaggle, enable **Internet**, optionally enable a GPU, and add `GROQ_API_KEY` and `GEMINI_API_KEY` through **Add-ons → Secrets**. Run the notebook cells in order. It installs FFmpeg and the lean dependencies, clones the project, starts FastAPI without opening a local browser, runs a Cloudflare quick tunnel, and prints a public URL without blocking the notebook cell.

The default **Edge TTS** engine is recommended for Kaggle because it avoids downloading a large local voice model. The optional VoxCPM2 cell is provided for GPU voice cloning and should only be run when that engine is selected in Settings. Kaggle output is ephemeral, so download finished videos before the session ends.

For a terminal-style launch from `/kaggle/working/recap-free`, use:

```bash
python kaggle_run.py
```

The launcher respects `RECAP_HOST`, `RECAP_PORT`, `RECAP_CONFIG_DIR`, `RECAP_DATA_DIR`, `GROQ_API_KEY`, and `GEMINI_API_KEY`. It returns immediately after starting the server and tunnel; there is no infinite keep-alive loop in the notebook.
