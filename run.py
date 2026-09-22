import os
import uvicorn


def main():
    host = os.getenv("RECAP_HOST", "0.0.0.0")
    port = int(os.getenv("RECAP_PORT", "8000"))
    print("=" * 60)
    print("   AI Video Dubbing & Subtitling Studio")
    print("   Groq STT • Gemini AI • Edge TTS & VoxCPM2 • FFmpeg")
    print("=" * 60)
    print(f"Starting server at http://{host}:{port} ...")
    # Do not open a browser in Kaggle/headless environments.
    uvicorn.run("app.main:app", host=host, port=port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
