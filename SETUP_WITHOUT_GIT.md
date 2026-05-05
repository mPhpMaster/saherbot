# تحميل وتثبيت SaherBot بدون Git

لا تحتاج إلى [Git](https://git-scm.com/) إن لم يكن مثبتاً. يمكنك أخذ نسخة المشروع كأرشيف ZIP من GitHub ثم تشغيل سكربت التثبيت على Windows.

**المستودع:** [https://github.com/mPhpMaster/saherbot](https://github.com/mPhpMaster/saherbot)

---

## المتطلبات

- **Windows 10/11** مع اتصال بالإنترنت.
- **PowerShell** (متوفر افتراضياً) — يُستخدم لتحميل ZIP في بعض الخطوات.
- **Python 3** ليس شرطاً مسبقاً: ملف **`install.bat`** يحاول تلقائياً:
  1. استخدام **Python** إن وُجد في PATH أو عبر أمر **`py -3`** أو في المسارات الشائعة للتثبيت.
  2. إن لم يجد شيئاً، يثبّت **Python 3.12** عبر **`winget`** (يتطلب تفعيل winget على النظام؛ قد يطلب صلاحيات مرة واحدة).
  3. ينشئ **`venv`** داخل المشروع ويثبّت من **`requirements.txt`** (`pyTelegramBotAPI`, `python-decouple`).
  4. ينشئ مجلدات **`logs`** و **`list`** وينسخ **`.env.example`** إلى **`.env`** عند الحاجة.

إذا لم يكن **winget** متوفراً وليس لديك Python، ثبّت Python يدوياً من [python.org](https://www.python.org/downloads/) مع خيار **Add python.exe to PATH** ثم أعد تشغيل **`install.bat`**.

---

## الطريقة 1: تحميل يدوي من المتصفح

1. افتح الرابط:  
   [https://github.com/mPhpMaster/saherbot/archive/refs/heads/main.zip](https://github.com/mPhpMaster/saherbot/archive/refs/heads/main.zip)  
   أو من صفحة الريبو: **Code → Download ZIP**.
2. فك الضغط؛ ستظهر مجلداً اسمه عادة **`saherbot-main`**.
3. ادخل المجلد وشغّل **`install.bat`** (نقرة مزدوجة).
4. عدّل ملف **`.env`** (ضع `BOT_TOKEN` و `CHAT_ID`).
5. شغّل **`run.bat`** لتشغيل البوت.

---

## الطريقة 2: أمر PowerShell (نسخ ولصق)

افتح PowerShell في المجلد الذي تريد أن يُنشأ فيه **`saherbot-main`** (مثلاً سطح المكتب):

```powershell
cd $env:USERPROFILE\Desktop
$url = 'https://github.com/mPhpMaster/saherbot/archive/refs/heads/main.zip'
$zip = Join-Path $env:TEMP 'saherbot-main.zip'
Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
Expand-Archive -Path $zip -DestinationPath (Get-Location) -Force
Remove-Item $zip
Set-Location .\saherbot-main
.\install.bat
```

بعد انتهاء التثبيت: عدّل `.env` ثم نفّذ `.\run.bat`.

> إذا كان مجلد `saherbot-main` موجوداً مسبقاً، احذفه يدوياً أو غيّر مجلد العمل قبل `Expand-Archive` لتفادي خلط الملفات.

---

## الطريقة 3: ملف `download-and-install.bat`

1. انسخ الملف **`download-and-install.bat`** من المشروع (أو حمّله من الريبو) إلى أي مجلد تريد أن يُفك فيه المشروع (مثلاً سطح المكتب أو مجلد فارغ).
2. شغّله بالنقر المزدوج.
3. سيُحمَّل أحدث **`main`** كـ ZIP، يُفك إلى **`saherbot-main`** بجانب الملف، ثم يُشغَّل **`install.bat`** تلقائياً.
4. بعدها عدّل `.env` داخل `saherbot-main` وشغّل **`run.bat`**.

---

## ملخص الأوامر (مع Git) — للمرجعية

من يريد استخدام Git:

```powershell
git clone https://github.com/mPhpMaster/saherbot.git
cd saherbot
.\install.bat
```

---

## روابط مباشرة

| الغرض | الرابط |
|--------|--------|
| أرشيف الفرع `main` (ZIP) | [archive/refs/heads/main.zip](https://github.com/mPhpMaster/saherbot/archive/refs/heads/main.zip) |
| صفحة المستودع | [github.com/mPhpMaster/saherbot](https://github.com/mPhpMaster/saherbot) |
