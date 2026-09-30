# RECAP FREE — Mode Audio Report

## Recap Mode

- မူရင်း human speech/dialogue ကို Demucs ဖြင့် လျှော့ဖယ်သည်။ Original music နှင့် sound effects ကို ဆက်ထားသည်။
- Gemini က movie recap narration အဖြစ် ပြန်ရေးသည်။
- ရွေးထားသော Edge TTS သို့မဟုတ် VoxCPM voice တစ်ခုတည်းဖြင့် ဖတ်သည်။
- ရွေးထားသော TTS narration ကို ကျန်နေသော music/SFX အောက်တွင် mix လုပ်သည်။
- Final video duration ကို TTS duration အတိုင်း speed ချိန်သည်။
- Short video များအတွက် natural expansion policy ရှိသော်လည်း 60 seconds ပြည့်အောင် မတမင်ထပ်မဖတ်ပါ။

## Story Mode

- မူရင်း video audio အားလုံးကို mute လုပ်သည်။ Music/SFX မပါပါ။
- User ပေးထားသော cinematic Burmese storytelling prompt ကိုသုံးသည်။
- အကျဉ်းချုပ်လွန်လွန်းခြင်းမရှိအောင် အရေးကြီးသော event, action, decision, emotion, danger, reveal နှင့် consequence များကို ထိန်းသည်။
- Source duration ကို minute-for-minute ပြန်မရေးပါ။ Long video များအတွက် target spoken script ကို ပုံမှန်အားဖြင့် source ၏ 60–70% ဝန်းကျင်ထားသည်။ ဥပမာ 9-minute video → ပုံမှန် 5–6 minutes ဝန်းကျင်။
- ရွေးထားသော Edge TTS သို့မဟုတ် VoxCPM voice တစ်ခုတည်းဖြင့် storytelling narration ဖတ်သည်။
- Original music/SFX မပါပါ။
- Final video duration ကို ထွက်လာသော TTS duration အတိုင်း exact speed match လုပ်သည်။

## Dubbing Mode

- Faster-Whisper transcript နှင့် timestamps ကိုသုံးသည်။
- Original vocal/dialogue ကို Demucs ဖြင့် လျှော့ဖယ်သည်။
- Original music နှင့် sound effects stem ကို ဆက်ထားသည်။
- Gemini က dialogue meaning ကို natural Burmese ဖြင့် ပြန်ရေးသည်။
- ကျား/မ auto speaker classification မသုံးပါ။ Pyannote gender classifier မသုံးပါ။
- လက်ရှိ Settings ထဲက ရွေးထားသော Edge voice သို့မဟုတ် VoxCPM voice တစ်ခုတည်းကို dialogue အားလုံးအတွက် သုံးသည်။
- Dubbing translation သည် source timing နီးစပ်အောင် ရေးရန် prompt ထားသည်။
- Background music/SFX နှင့် TTS ကို mix ပြီး Final video duration ကို TTS duration အတိုင်းညှိသည်။

## Shared Settings

Mode သုံးခုလုံးသည် Settings အသစ်ခွဲမထားဘဲ လက်ရှိ Voice Engine, Voice, Target Language, Subtitle, Font, Color, Blur နှင့် Resolution settings တစ်ခုတည်းကို share လုပ်သည်။
