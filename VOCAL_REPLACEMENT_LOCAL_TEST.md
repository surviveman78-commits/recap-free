# Vocal-Replacement Mode — Local Test Report

**Status:** Local-only; GitHub မတင်ရသေးပါ။

## လုပ်ထားသော flow

လက်ရှိ recap renderer သည် default အနေဖြင့် မူရင်း audio track တစ်ခုလုံးကို map မလုပ်ဘဲ TTS audio တစ်ခုတည်းဖြင့် video ကို mux လုပ်သည်။ အသစ်ထည့်ထားသော optional mode ကိုဖွင့်လျှင် အောက်ပါ flow ကိုသုံးသည်။

```text
Original video stereo/high-quality audio (2ch, 44.1 kHz)
  → Demucs htdemucs two-stem separation
  → vocals ကို လျှော့ဖယ်ထားသော no_vocals.wav
  → TTS narration နှင့် background stem ကို FFmpeg amix
  → original video + mixed audio mux
```

မူရင်း mode မပျက်စေရန် `preserve_original_background` သည် default `false` ဖြစ်သည်။ UI Voice settings မှ **“မူရင်း music/effects ထိန်းပြီး vocal ကိုသာ လျှော့ဖယ်ကာ TTS ပေါင်းမယ်”** ကို ဖွင့်မှ mode အသစ်သုံးမည်။

## ပြင်ထားသောဖိုင်များ

- `app/pipeline/vocal_separator.py` — Demucs `htdemucs` two-stem separation
- `app/pipeline/audio_mixer.py` — background stem + TTS `amix`
- `app/pipeline/orchestrator.py` — optional vocal-replacement stage
- `app/main.py` — JSON/Form API option
- `app/queue_manager.py` — job option forwarding
- `app/config.py` — default setting
- `static/index.html` — Voice settings toggle
- `static/js/app.js` — settings save and URL/upload job payload
- `requirements.txt` — `demucs>=4.0.1`
- `requirements-kaggle.txt` — `demucs>=4.0.1`

## Local test result

Synthetic 4-second stereo audio/video ဖြင့် စမ်းသပ်ခဲ့သည်။ မူရင်း audio ထဲတွင် voice-like tone နှင့် background bed နှစ်မျိုးပေါင်းထားပြီး Demucs ဖြင့် `no_vocals.wav` ထုတ်သည်။ ထို background stem ကို synthetic TTS track နှင့် ပြန်ပေါင်းပြီး final MP4 ထုတ်ခဲ့သည်။

```text
Full-quality source: 2 channels, 44.1 kHz
Demucs background stem: created
Final MP4: created
Final duration: 4.000000 seconds
Python compile: passed
JavaScript syntax check: passed
FFmpeg render: passed
```

## သတိပြုရန်

Demucs သည် speech/music separation ကို AI ဖြင့် ခန့်မှန်းခြင်းဖြစ်သောကြောင့် မူရင်း voiceover နှင့် background music/SFX တစ်ခုနှင့်တစ်ခု အလွန်ရောနေပါက residual vocal သို့မဟုတ် music leakage အနည်းငယ်ရှိနိုင်သည်။ သို့သော် ယခင်လို မူရင်း audio အားလုံးကိုဖျောက်ပြီး TTS တစ်ခုတည်းထည့်ခြင်းထက် သင်လိုချင်သည့် **မူရင်း music/effects ကို ထိန်းပြီး voiceover ကိုသာအစားထိုး** သည့်ပုံစံဖြစ်သည်။

## Deployment note

Kaggle တွင် `requirements-kaggle.txt` မှတစ်ဆင့် Demucs ကို install လုပ်ရမည်။ Demucs model ကို ပထမဆုံး run ချိန်တွင် download လုပ်နိုင်ပြီး GPU ရှိပါက GPU၊ မရှိပါက CPU သုံးမည်။
