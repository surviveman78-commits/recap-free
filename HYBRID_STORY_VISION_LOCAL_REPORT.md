# Hybrid Story Mode Vision Analysis — Local Report

Date: 2026-10-05

## Requested flow

ပုံမှန်အတိုင်း Whisper transcript အရင်ထုတ်သည်။ Transcript ရှိသောအပိုင်းများကို Story Mode storytelling logic ဖြင့် ဆက်လုပ်သည်။ Transcript မရှိသော gap များကိုသာ Gemini Vision ဖြင့် frame သုံးခုစီ စစ်ပြီး plot အတွက်အရေးကြီးသော action ရှိမှ Story context ထဲ ထည့်သည်။ ထို့နောက် ပုံမှန် Story rewriter က transcript နှင့် visual action context ကိုပေါင်းပြီး narrator script ပြန်ရေးသည်။

## Changed files

### `app/pipeline/gemini_action_analyzer.py`

Selective Vision analyzer အသစ်ထည့်ထားသည်။

- Whisper segment ကြား gap 2.5 seconds နှင့်အထက်ကို ရှာသည်
- 45 seconds ထက်ရှည်သော gap ကို bounded windows ခွဲသည်
- Gap တစ်ခုစီအတွက် beginning/middle/end frame ၃ ခုထုတ်သည်
- Gemini Vision ကို frame set သုံးခုလုံးပို့သည်
- မြင်ရသော story-relevant action ရှိမှသာ result ထုတ်သည်
- Confidence 0.70 အောက် result ကို ပယ်သည်
- Name, dialogue, motive, thought, identity မမြင်ရလျှင် မခန့်မှန်းစေရန် prompt guard ထည့်ထားသည်
- `story_action_analysis.json` အဖြစ် gap နှင့် visual segment metadata သိမ်းသည်

### `app/pipeline/orchestrator.py`

Whisper transcription ပြီးသည့်နောက် **Story Mode branch တစ်ခုတည်း** တွင် `GeminiActionGapAnalyzer` ခေါ်ထားသည်။ Vision result များကို `role=visual_action` နှင့် original start/end timestamps ဖြင့် transcript segments ထဲ ပေါင်းပြီး Gemini Story rewriter သို့ ပို့သည်။ Vision API/network/model error ဖြစ်ပါက ပုံမှန် transcript-only Story flow သို့ fallback လုပ်သည်။

Story Mode သည် source video duration ကို timing rule အတွက် ဆက်အသုံးပြုသည်။ Recap နှင့် Dubbing branch များသည် Vision analyzer ကို မခေါ်ပါ။

## Resulting flow

```text
Video
→ Audio extraction
→ Whisper transcript
→ Story Mode only: transcript-free gaps detect
→ Gap တစ်ခုစီမှာ Gemini Vision frame ၃ ခုစစ်
→ Meaningful visual actions သာ context ထဲထည့်
→ Existing Story rewriter
→ TTS
→ Existing scene/timeline rendering
```

## Local tests

### Gap detection — PASS

- Transcript မရှိသော beginning/middle/end gap များတွေ့သည်
- 2.5 seconds အောက် gap များကို မခေါ်
- 45 seconds ထက်ရှည် gap များကို bounded windows ခွဲသည်

### Mock Vision analysis — PASS

- Synthetic transcript gap နှစ်ခုအတွက် mock action result ထုတ်နိုင်သည်
- `role=visual_action` segment များရသည်
- `story_action_analysis.json` ရေးနိုင်သည်

### Mode isolation — PASS

- Orchestrator တွင် Vision branch သည် `processing_mode == "story"` အောက်တွင်သာရှိသည်
- Recap နှင့် Dubbing များသည် Vision branch မဝင်ပါ

### Existing regression — PASS

```bash
python3 test_pipeline.py
```

Audio extraction, TTS, video speed matching, subtitle burn-in, font endpoint နှင့် voice-reference endpoint အားလုံး pass ဖြစ်သည်။

## GitHub status

**မတင်ရသေးပါ။** Local working tree တွင်သာရှိသည်။

## Important limitation

Local environment တွင် real Gemini Vision API နှင့် real movie end-to-end test မလုပ်ရသေးပါ။ Mock Vision test နှင့် existing regression test များသာ run ထားသည်။ Kaggle/local မှာ Story Mode real video တစ်ပုဒ်ဖြင့် action-only gap result နှင့် final narration timing ကို ထပ်စစ်ရန်လိုသည်။
