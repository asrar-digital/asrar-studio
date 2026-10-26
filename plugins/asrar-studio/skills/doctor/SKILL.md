---
name: doctor
description: يفحص جهاز المستخدم ويجهّز أدوات أسرار ستوديو (ffmpeg، Node.js، التفريغ، محرّك الرسم). استخدمه لما يقول «افحص أسرار ستوديو»، «جهّز الأداة»، أو أول مرة يستخدم الأداة.
---

# فحص وتجهيز أسرار ستوديو

1. شغّل: `python "${CLAUDE_PLUGIN_ROOT}/engine/studio.py" doctor`
2. لكل أداة ناقصة: قل له بجملة وش هي وليش نحتاجها، **وخذ موافقته** قبل التثبيت:
   - ويندوز: `winget install Gyan.FFmpeg` · `winget install OpenJS.NodeJS.LTS` · `pip install faster-whisper numpy`
   - ماك: `brew install ffmpeg node` · `pip3 install faster-whisper numpy`
   - بعد تثبيت ffmpeg أو Node على ويندوز: **لازم يسكّر Claude Code ويفتحه** عشان يشوفها.
3. محرّك الرسم: `studio.py setup` (~500 ميقا، مرة وحدة).
4. أعد `doctor` لين تطلع «كل شي جاهز 🎬».
5. أول تفريغ ينزّل نموذج اللغة (~3 قيقا) — قل له قبلها.
