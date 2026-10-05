# Scene-by-Scene Synchronization — Local Report

Date: 2026-10-05

## Why this change was needed

အရင် flow က video တစ်ခုလုံးနှင့် TTS တစ်ခုလုံးကို global `setpts` factor တစ်ခုတည်းဖြင့် stretch/compress လုပ်သည်။ Video ရှည်လာသောအခါ scene တစ်ခုအတွင်း ဖြစ်ပေါ်သည့် timing difference သည် နောက်ပိုင်း scene များအထိ စုပေါင်းသွားနိုင်သဖြင့် scene နှင့် narration တဖြည်းဖြည်း မကိုက်တော့နိုင်သည်။

## Local changes

### `app/pipeline/tts_engine.py`

TTS segment များကို assemble လုပ်စဉ်တွင် TTS clock အပြင် မူရင်း transcript/video clock ကိုလည်း synced segment ထဲ သိမ်းထားသည်။ အခု synced segment တစ်ခုတွင် `start/end` (TTS timeline) နှင့် `source_start/source_end` (original video timeline) နှစ်မျိုးရှိသည်။

### `app/pipeline/audio_mixer.py`

Video duration 120 seconds နှင့်အထက်ဖြစ်ပြီး source timeline metadata ပါသော segments လုံလောက်ပါက scene-like groups တည်ဆောက်သည်။ Group boundary သည် transcript gap 2 seconds ဝန်းကျင် သို့မဟုတ် group span 30 seconds ရောက်သောအခါ ခွဲသည်။

Group တစ်ခုချင်းစီအတွက် video scene ကို trim လုပ်ပြီး အဲ့ဒီ group ၏ TTS duration နှင့်သာ speed ညှိသည်။ ထို့နောက် video scenes များကို concat လုပ်သည်။ Music/SFX background stem ကိုလည်း အတူတူ source scene အလိုက် trim၊ retime၊ concat ပြီး TTS နှင့် mix လုပ်သည်။ Source gap များကို မဖျက်ဘဲ နောက် group ထဲ ဆက်ထည့်ထားသည်။

Video 120 seconds မပြည့်သော job များ၊ source metadata မပြည့်သော job များတွင် အရင် global timing flow ကို safe fallback အဖြစ် ဆက်သုံးသည်။ ထို့ကြောင့် short-video behavior မပြောင်းပါ။

### `app/pipeline/orchestrator.py`

TTS မှရသော synced segments ကို AudioMixer သို့ ပို့ထားသည်။ Existing subtitle/blur/output settings မပြောင်းပါ။

## Tests

### Scene grouping unit test — PASS

- 120 seconds မပြည့်သော video တွင် legacy path သို့ fallback
- Long-video sample တွင် multiple groups ဖန်တီးနိုင်
- First group ကို source/TTS time 0 မှစ
- Last group ကို source video/TTS audio အဆုံးအထိ ရောက်
- Source gap မပျောက်

### Forced scene render test — PASS

Long-video graph ကို 5-second fixture ပေါ် force လုပ်ပြီး FFmpeg scene video concat နှင့် background-audio concat ကို စမ်းထားသည်။ Output 4.0 seconds ထွက်ပြီး file valid ဖြစ်သည်။

### Existing regression test — PASS

`python3 test_pipeline.py` ဖြင့် audio extraction, TTS, video slowdown/speed-up, subtitle burn-in, font upload နှင့် voice-reference upload အားလုံး pass ဖြစ်သည်။

## Not changed

- Recap/Story/Dubbing mode settings များ
- Subtitle style, position, blur settings
- 4K filter နှင့် 7-second mirror mode
- NVENC/CPU fallback policy
- GitHub repository

## GitHub status

**မတင်ရသေးပါ။** Local working tree တွင်သာ ပြင်ထားသည်။

## Important limitation

Scene boundary သည် လက်ရှိ transcript timestamps နှင့် silence/gap heuristic ကို အခြေခံသည်။ Real movie တစ်ပုဒ်ဖြင့် long-video end-to-end test မလုပ်ရသေးပါ။ Kaggle/local တွင် 3–5 မိနစ်နှင့်အထက် video တစ်ပုဒ်စမ်းပြီး scene boundaries နှင့် final sync ကို ထပ်စစ်သင့်သည်။
