import sys
import os
import time
import webbrowser
import threading
import uvicorn

def open_browser():
    time.sleep(1.2)
    webbrowser.open("http://127.0.0.1:8000")

def main():
    print("=" * 60)
    print("   AI Video Dubbing & Subtitling Studio")
    print("   Groq STT • Gemini AI • Edge TTS & VoxCPM2 • FFmpeg")
    print("=" * 60)
    print("Starting server at http://127.0.0.1:8000 ...")

    threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()
