
## ၉။ Local implementation update

Short-video expansion trigger ကို local code တွင် ပြင်ဆင်ထားသည်။

- မူရင်း video file အရှည်ကိုသာ မသုံးတော့ပါ။
- Whisper transcript segment များထဲမှ နောက်ဆုံး spoken segment ၏ `end` timestamp ကို အသုံးပြုသည်။
- Video ထဲတွင် နောက်ဆုံးပိုင်း silent tail ရှိသော်လည်း spoken transcript က ၄၀/၅၀ စက္ကန့်သာဆိုလျှင် short-video rule အလုပ်လုပ်မည်။
- Cloud API / Gemini mode တွင် transcript duration `< 60 seconds` ဖြစ်ပါက Gemini ကို အဓိပ္ပါယ်မပျက်ဘဲ narration ကို ၆၀ စက္ကန့်ကျော်အောင် သဘာဝကျကျ ချဲ့ရေးခိုင်းမည်။
- TTS engine သည် segment တစ်ခုချင်းကို တစ်ကြိမ်သာ ဖတ်မည်။ Duplicate/repeat logic မထည့်ထားပါ။
- Numeric/TTS local changes နှင့် short-video trigger change များကို GitHub သို့ မတင်ရသေးပါ။
