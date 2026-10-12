# Story Mode Scene-Aware Selective Narration — Local Report

Date: 2026-10-05

## Goal

Story Mode တွင် transcript စာကြောင်းတိုင်းကို တစ်ကြောင်းချင်းဘာသာပြန်ခြင်းမလုပ်ဘဲ scene အပြည့်ကို အရင်နားလည်ပြီး viewer သိရန်လိုအပ်သော story beats များကိုသာ Burmese narrator အဖြစ် ပြန်ရေးရန် ပြင်ထားသည်။

## Changed file

- `app/pipeline/gemini_rewriter.py`

## Story Mode behavior

Story prompt သည် scene တစ်ခုလုံးကို setup, action, reaction, decision, reveal, consequence အဖြစ် အရင်ခွဲစဉ်းစားစေသည်။ Plot ပြောင်းစေသော action, character motive, conflict, emotion, reveal နှင့် cause-and-effect ကို ထိန်းထားပြီး greeting, filler, repeated explanation, small-talk, duplicate reaction နှင့် long pause များကို ချုံ့စေသည်။

Dialogue အားလုံးကို line-by-line မပြန်တော့ဘဲ အရေးကြီးသောအဓိပ္ပာယ်နှင့် consequence ကို narrator sentence တိုများဖြင့် ပြန်ရေးစေသည်။ Long scene တစ်ခုအတွင်း action များစွာရှိပါက chronological order နှင့် short transitions အသုံးပြုစေသည်။

JSON timeline alignment မပျက်စေရန် input segment id/start/end များကို ဆက်ထိန်းထားပြီး segment text ကိုသာ concise narrator wording ဖြစ်အောင် ချိန်ထားသည်။

## Recap protection

Recap Mode တွင် ရှိပြီးသား faithful source-coverage policy ကို မပြောင်းပါ။ Recap သည် transcript information မပျောက်အောင် sentence/proposition အပြည့် ပြန်ရေးသည့် flow အတိုင်း ဆက်ရှိသည်။ Selective coverage policy သည် Story Mode တစ်ခုတည်းအတွက်သာ prompt ထဲ ဝင်သည်။

## Local verification

Selective Story prompt contract test: **PASS**

- Story prompt တွင် `STORY MODE COVERAGE POLICY` ပါသည်
- Dialogue line-by-line translation မလုပ်ရန် rule ပါသည်
- Story တွင် concise narrator wording rule ပါသည်
- Recap prompt တွင် Story-only policy မဝင်ပါ
- Recap ရဲ့ `SOURCE-COVERAGE SAFETY` policy ဆက်ရှိသည်

Existing regression test: **PASS**

```bash
python3 test_pipeline.py
```

Video speed matching, audio extraction, TTS, subtitle burn-in, font endpoint နှင့် voice-reference endpoint အားလုံး pass ဖြစ်သည်။

## Scope and limitation

ဤပြင်ဆင်မှုသည် Gemini Story prompt နှင့် coverage policy ကို ပြင်ခြင်းဖြစ်ပြီး mode settings, subtitle, blur, render resolution နှင့် Dubbing flow များကို မပြောင်းပါ။ Real 3-minute movie transcript ဖြင့် Gemini output quality ကို မစမ်းရသေးသောကြောင့် local/Kaggle တွင် real video တစ်ပုဒ်ဖြင့် ထပ်စမ်းရန်လိုသည်။

## GitHub status

**မတင်ရသေးပါ။** Local working tree တွင်သာရှိသည်။
