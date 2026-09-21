import os
import shutil
import subprocess
import soundfile as sf
import numpy as np
from pathlib import Path

from app.pipeline.audio_extractor import AudioExtractor
from app.pipeline.audio_mixer import AudioMixer
from app.pipeline.subtitle_burner import SubtitleBurner
from app.pipeline.tts_engine import TTSEngine
from fastapi.testclient import TestClient
from app.main import app


def test_complete_suite():
    print("==================================================")
    print("   TESTING VIDEO RECAP & SPEED SYNCHRONIZATION")
    print("==================================================")

    test_dir = Path("temp/suite_test")
    test_dir.mkdir(parents=True, exist_ok=True)

    # 1. Test Synthetic Video Creation (5 seconds)
    print("\n[Test 1] Creating Synthetic 5-second Video...")
    video_5s = test_dir / "input_5s.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=navy:s=720x1280:d=5",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
        "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        str(video_5s)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert video_5s.exists()
    print("  -> Synthetic 5s video created successfully.")

    # 2. Test Audio Extraction
    print("\n[Test 2] Testing Audio Extraction...")
    extractor = AudioExtractor()
    extracted = extractor.extract(video_5s)
    assert extracted.exists() and extracted.stat().st_size > 0
    print(f"  -> Extracted audio: {extracted.name}")

    # 3. Test Continuous Recap TTS Generation
    print("\n[Test 3] Testing Continuous Recap TTS Generation...")
    tts_engine = TTSEngine()
    segments = [
        {"id": 0, "start": 0.0, "end": 2.0, "text": "This is the first sentence of the recap story."},
        {"id": 1, "start": 2.2, "end": 4.0, "text": "The recap narration flows naturally without gaps."}
    ]
    tts_audio, synced_segs = tts_engine.generate(
        segments=segments,
        output_dir=test_dir,
        engine="edge_tts",
        voice="en-US-ChristopherNeural"
    )
    assert tts_audio.exists() and tts_audio.stat().st_size > 0
    tts_dur = sf.info(str(tts_audio)).duration
    print(f"  -> Generated Continuous TTS: {tts_dur:.2f}s with {len(synced_segs)} synced segments.")

    # 4. Test Video Speed Stretching (setpts) - Case A: Slow Down Video (Video 5s -> Audio 7s)
    print("\n[Test 4] Testing Video Speed Slowdown (setpts: 5s video -> 7s audio)...")
    mixer = AudioMixer()
    audio_7s = test_dir / "long_7s.wav"
    sf.write(str(audio_7s), np.zeros(44100 * 7, dtype=np.int16), 44100)
    out_slowed = test_dir / "video_slowed.mp4"
    mixer.mix(video_5s, audio_7s, out_slowed)
    assert out_slowed.exists()
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(out_slowed)
    ]
    dur_slowed = float(subprocess.run(cmd, stdout=subprocess.PIPE, text=True).stdout.strip())
    print(f"  -> Video slowed down to: {dur_slowed:.2f}s (Target: 7.0s)")
    assert abs(dur_slowed - 7.0) < 0.2, f"Expected ~7.0s, got {dur_slowed}"

    # 5. Test Video Speed Speedup (setpts) - Case B: Speed Up Video (Video 5s -> Audio 3s)
    print("\n[Test 5] Testing Video Speed Speedup (setpts: 5s video -> 3s audio)...")
    audio_3s = test_dir / "short_3s.wav"
    sf.write(str(audio_3s), np.zeros(44100 * 3, dtype=np.int16), 44100)
    out_spedup = test_dir / "video_spedup.mp4"
    mixer.mix(video_5s, audio_3s, out_spedup)
    assert out_spedup.exists()
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(out_spedup)
    ]
    dur_spedup = float(subprocess.run(cmd, stdout=subprocess.PIPE, text=True).stdout.strip())
    print(f"  -> Video sped up to: {dur_spedup:.2f}s (Target: 3.0s)")
    assert abs(dur_spedup - 3.0) < 0.2, f"Expected ~3.0s, got {dur_spedup}"

    # 6. Test Interactive Subtitle Burning with Exact pos(x,y) Drag Coordinates
    print("\n[Test 6] Testing Subtitle Burning with drag coordinates pos(45%, 75%)...")
    burner = SubtitleBurner()
    final_burned = test_dir / "final_recap.mp4"
    burner.burn(
        video_path=out_slowed,
        segments=synced_segs,
        output_path=final_burned,
        font_color="#00FFFF",  # Cyan
        font_size_px=42,
        font_style="Myanmar Text",
        pos_x_pct=45.0,
        pos_y_pct=75.0
    )
    assert final_burned.exists() and final_burned.stat().st_size > 0
    print(f"  -> Final burned video created: {final_burned} ({final_burned.stat().st_size} bytes)")

    # 7. Test FastAPI Endpoints: Custom Font Upload & VoxCPM Reference Text
    print("\n[Test 7] Testing FastAPI Endpoints...")
    client = TestClient(app)

    # Test VoxCPM reference upload with reference text
    dummy_audio = test_dir / "test_speaker.wav"
    sf.write(str(dummy_audio), np.zeros(16000, dtype=np.int16), 16000)
    with open(dummy_audio, "rb") as f:
        r_vox = client.post(
            "/api/voices/upload-reference",
            files={"file": ("test_speaker.wav", f, "audio/wav")},
            data={"reference_text": "This is the sample speaker reference text for VoxCPM."}
        )
    assert r_vox.status_code == 200
    assert r_vox.json()["reference_text"] == "This is the sample speaker reference text for VoxCPM."
    print("  -> POST /api/voices/upload-reference with text: OK")

    # Test Custom Font Upload
    dummy_font = test_dir / "CustomPyidaungsu.ttf"
    with open(dummy_font, "wb") as f:
        f.write(b"\x00\x01\x00\x00dummyfontbytes")
    with open(dummy_font, "rb") as f:
        r_font = client.post("/api/fonts/upload", files={"file": ("CustomPyidaungsu.ttf", f, "font/ttf")})
    assert r_font.status_code == 200
    assert r_font.json()["font_name"] == "CustomPyidaungsu"
    print("  -> POST /api/fonts/upload: OK")

    # Verify font appears in /api/fonts
    r_fonts = client.get("/api/fonts")
    assert r_fonts.status_code == 200
    assert "CustomPyidaungsu" in r_fonts.json()["fonts"]
    print("  -> Custom font verified in /api/fonts catalog: OK")

    # Cleanup temp
    shutil.rmtree("temp", ignore_errors=True)
    print("\n==================================================")
    print("   ALL RECAP & SYNC TESTS PASSED WITH 100% SUCCESS!")
    print("==================================================")


if __name__ == "__main__":
    test_complete_suite()
