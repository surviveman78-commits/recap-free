# RECAP Mode Change Report

**Status:** Local only — GitHub မတင်ရသေးပါ။

## အတည်ပြုထားသော Recap Mode behavior

Recap Mode ၏ မူရင်း recap writing style နှင့် လက်ရှိ pipeline flow ကို မပြောင်းထားပါ။ Gemini recap prompt, TTS voice flow, Burmese number pronunciation, subtitle, font, blur, resolution နှင့် duration policy များကို Recap Mode အတွက် မပြောင်းထားပါ။

ပြောင်းထားသည့်အဓိကအချက်မှာ audio rendering တစ်ခုတည်းဖြစ်သည်။ မူရင်း video ထဲမှ human speech/dialogue ကို Demucs ဖြင့် လျှော့ဖယ်ပြီး မူရင်း background music နှင့် sound effects ကို ဆက်ထားသည်။ ထို background stem အပေါ်တွင် Recap TTS narration ကို ပြန်ပေါင်းသည်။

```text
Original video audio
  → Demucs vocal/dialogue separation
  → no_vocals.wav = music + sound effects
  → Recap TTS + music/SFX mix
  → final video
```

## Recap Mode အတွက် မပြောင်းထားသောအရာများ

| အပိုင်း | အခြေအနေ |
|---|---|
| Recap writing style | မူရင်းအတိုင်း |
| Gemini recap prompt | မူရင်းအတိုင်း |
| TTS engine / selected voice | မူရင်းအတိုင်း |
| Burmese number pronunciation | မူရင်းအတိုင်း |
| Subtitle / font / color | မူရင်းအတိုင်း |
| Blur behavior | မူရင်းအတိုင်း |
| Output resolution | မူရင်းအတိုင်း |
| Short-video expansion policy | မူရင်းအတိုင်း |
| Speaker gender detection | မထည့်ထား |
| Story Mode prompt | Recap Mode ကို မသက်ရောက် |
| Dubbing Mode behavior | Recap Mode ကို မသက်ရောက် |

## Audio behavior by mode

- **Recap:** human speech/dialogue ဖယ်၊ music + SFX ကျန်၊ Recap TTS ပြန်ပေါင်း။
- **Story:** original audio အားလုံး mute၊ Story TTS တစ်ခုတည်းသုံး။ Long video များအတွက် controlled storytelling duration။
- **Dubbing:** human speech/dialogue ဖယ်၊ music + SFX ကျန်၊ ဘာသာပြန် TTS ပြန်ပေါင်း။ Gender auto-classification မသုံး။

## Local verification

- `app/pipeline/orchestrator.py` တွင် Recap နှင့် Dubbing အတွက် background stem ကိုအသုံးပြုပြီး Story Mode တစ်ခုတည်းတွင်သာ original audio stem မသုံးကြောင်း စစ်ပြီး။
- `app/pipeline/vocal_separator.py` သည် Whisper အတွက်သုံးသော mono 16 kHz copy မဟုတ်ဘဲ original stereo 44.1 kHz source ကို Demucs ဆီပို့သည်။
- Python compile — passed။
- JavaScript syntax check — passed။
- Git diff check — passed။
- GitHub push — မလုပ်ရသေးပါ။
