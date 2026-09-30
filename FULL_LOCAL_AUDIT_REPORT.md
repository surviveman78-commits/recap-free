# RECAP FREE — Full Local Audit Report

**Audit date:** 2026-09-30
**Environment:** `/home/ubuntu/recap-free-local`
**Deployment status:** Local only. GitHub push မလုပ်ရသေးပါ။

## Executive result

Local project ကို changed files, mode routing, API/queue, TTS/duration, audio separation, UI payload, requirements, syntax နှင့် regression tests အားလုံး ပြန်စစ်ပြီးပါပြီ။ လက်ရှိ implementation သည် Recap, Story, Dubbing mode သုံးခုကို shared settings ဖြင့် ခွဲသုံးနိုင်သည်။ Recap Mode ၏ မူရင်း writing flow မပြောင်းဘဲ audio routing ကို music/SFX preservation အဖြစ်ထည့်ထားသည်။

## Final mode behavior

| Mode | Writing behavior | Original audio behavior | Final duration |
|---|---|---|---|
| Recap | လက်ရှိ recap prompt/flow မပြောင်း | Demucs ဖြင့် human speech/dialogue ဖယ်၊ music/SFX ကျန်၊ Recap TTS ပြန်ပေါင်း | TTS duration အတိုင်း |
| Story | User ပေးထားသော cinematic Burmese storytelling prompt; long video ကို အလွန်အကျဉ်းမချုပ်ဘဲ long source အတွက် 60–70% target | Original audio အားလုံး mute; TTS တစ်ခုတည်း | Final TTS duration အတိုင်း |
| Dubbing | Source dialogue meaning/timing ကိုထိန်းပြီး natural Burmese ပြန်ရေး | Demucs ဖြင့် human speech/dialogue ဖယ်၊ music/SFX ကျန်၊ Dubbing TTS ပြန်ပေါင်း | TTS duration အတိုင်း |

Story Mode သည် Gemini Story prompt လိုအပ်သောကြောင့် Gemini API key မရှိလျှင် job queue မတင်ဘဲ API မှာရှင်းလင်းသော error ပြသည်။ Recap နှင့် Dubbing တို့တွင် local NLLB/Gemini ရှိပြီးသား behavior ကို မပြောင်းထားပါ။

## Backend audit

### Orchestrator

`PipelineOrchestrator` သည် `processing_mode` ကို လက်ခံပြီး mode အလိုက် translation branch နှင့် audio branch ကို ခွဲသည်။ Recap/Dubbing တွင် original stereo mix ကို 44.1 kHz ဖြင့်ထုတ်ပြီး Demucs `no_vocals.wav` ကို background stem အဖြစ်သုံးသည်။ Story တွင် Demucs မခေါ်ဘဲ original audio stem မထည့်ပါ။

Story mode တွင် Gemini key မရှိလျှင် အလုပ်မစခင် `Story Mode အတွက် Gemini API Key လိုအပ်ပါသည်` error ပြသည်။

### Queue/API

JSON link job နှင့် multipart file-upload job နှစ်ခုလုံးတွင် `processing_mode` ကိုလက်ခံပြီး `recap`, `story`, `dubbing` သုံးခုထဲမှမဟုတ်လျှင် `recap` သို့ fallback လုပ်သည်။ Queue သည် mode ကို orchestrator ဆီပို့သည်။ Story mode အတွက် Gemini key preflight ကို route အဆင့်မှာလည်း စစ်ထားသည်။

`preserve_original_background` field သည် backwards compatibility အတွက် ကျန်နေသော်လည်း current mode audio rule က mode ကို အဓိကထားသည်: Story = no background stem; Recap/Dubbing = background stem.

### Audio mixer

`AudioMixer` သည် TTS duration နှင့် original video duration ကိုတွက်ပြီး `setpts` ဖြင့် video speed ကို TTS duration သို့ညှိသည်။ Background stem ရှိပါက TTS နှင့် `amix` လုပ်သည်။ Background stem မရှိပါက TTS audio တစ်ခုတည်းကို map လုပ်သည်။ GPU encoder မအောင်မြင်ပါက libx264 CPU fallback ရှိသည်။

### Vocal separator

`VocalSeparator` သည် Whisper အတွက်သုံးသော mono 16 kHz copy ကို မသုံးဘဲ original stereo 44.1 kHz audio ကို extract လုပ်သည်။ Demucs `htdemucs --two-stems=vocals` ဖြင့် `no_vocals.wav` ထုတ်သည်။

## Gemini and timing audit

- Recap mode branch သည် existing recap instruction ကို ဆက်သုံးသည်။
- Story mode တွင် user-provided cinematic Burmese storytelling prompt ထည့်ထားသည်။
- Story long-video rule သည် source ကို minute-for-minute မကူးဘဲ key events မပျောက်စေဘဲ source duration 60–70% ဝန်းကျင် target ထားသည်။ ဥပမာ 9-minute video → ပုံမှန် 5–6 minutes ဝန်းကျင်။
- Dubbing mode သည် source dialogue timing နှင့်နီးစပ်အောင်ရေးရန် rule သုံးသည်။
- Recap အတွက် အရင် natural-length rule ကို မပြောင်းထားပါ။

## Frontend audit

- Mode cards များကို Subtitle Burn-in အောက်တွင်ထားသည်။
- Recap card: `music/SFX ကျန်`.
- Story card: `မူရင်းအသံဖျောက်`.
- Dubbing card: `Dialogue ဘာသာပြန်`.
- Selected mode ကို JSON link request နှင့် FormData upload request နှစ်ခုလုံးတွင် ပို့သည်။
- Mobile responsive CSS ထည့်ထားသည်။
- Existing subtitle, font, blur, color, resolution controls များကို mode အတွက် မဖျက်ထားပါ။

## Files changed or added

- `app/main.py` — mode fields, Story Gemini preflight, queue payload.
- `app/queue_manager.py` — mode persistence and orchestrator payload.
- `app/pipeline/orchestrator.py` — mode translation branch and audio routing.
- `app/pipeline/gemini_rewriter.py` — Story prompt and Story/Dubbing timing rules.
- `app/pipeline/audio_mixer.py` — optional background stem mixing.
- `app/pipeline/vocal_separator.py` — new Demucs stereo source/background adapter.
- `app/config.py` — mode/background settings defaults.
- `requirements.txt`, `requirements-kaggle.txt` — Demucs dependency.
- `static/index.html`, `static/recap.html` — mode card UI.
- `static/css/style.css` — mode card styling.
- `static/js/app.js` — mode state and request payload.
- `MODE_AUDIO_REPORT.md` — mode audio reference.
- `RECAP_MODE_CHANGE_REPORT.md` — Recap-only change report.
- `VOCAL_REPLACEMENT_LOCAL_TEST.md` — vocal replacement notes.

## Tests performed

| Test | Result |
|---|---|
| Python compile: main, queue, orchestrator, Gemini, mixer, separator | Passed |
| JavaScript `node --check` | Passed |
| `git diff --check` | Passed |
| Existing `test_pipeline.py` | Passed: synthetic video, extraction, Edge TTS, slow/fast speed match, subtitle burn, API uploads |
| 5s video → 7s TTS | Passed: 7.00s output |
| 5s video → 3s TTS | Passed: 3.00s output |
| Story-style no-background 90s → 60s TTS | Passed: 60.000s output, one audio stream |
| Background mix duration test | Passed: TTS/background mix output matched TTS duration |
| OpenAPI job endpoints | Passed |
| Demucs CLI availability | Passed |
| Actual Demucs synthetic separation | Passed: `no_vocals.wav` produced |
| `VocalSeparator` class extraction + separation integration | Passed |
| Local preview UI and mode click state | Passed |

The existing test suite emitted only a Starlette/httpx deprecation warning; it did not cause a test failure.

## Remaining verification boundary

No real user video was processed during this audit. Actual quality of vocal removal depends on the source mix: heavily overlapping speech, reverb, or music with vocals may leave artifacts because Demucs is source-separation based. Gemini Story output quality and Edge/VoxCPM audio quality still depend on configured API/model availability. Kaggle runtime should install the updated requirements before deployment.

## Final status

- Local code: syntax and regression checks passed.
- Audio routing: implemented and integration-tested.
- Mode UI: implemented and preview-tested.
- Story Gemini key preflight: implemented.
- GitHub push: **not performed**.
