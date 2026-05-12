# تحميل وتثبيت SaherBot بدون Git

لا تحتاج إلى [Git](https://git-scm.com/) إن لم يكن مثبتاً. خذ المشروع كأرشيف ZIP من GitHub ثم شغّل سكربت التثبيت.

**المستودع:** [https://github.com/mPhpMaster/saherbot](https://github.com/mPhpMaster/saherbot)

للملخص الإنجليزي: [README.md](README.md) · للتفاصيل التقنية: [DOCUMENTATION.md](DOCUMENTATION.md).

---

## المتطلبات

- **Windows 10/11** مع اتصال بالإنترنت (لهذا الدليل؛ على Linux/macOS راجع قسم **مع Git** أدناه).
- **PowerShell** — يُستخدم لتحميل وفك الضغط في بعض الخطوات.
- **Python 3** ليس شرطاً مسبقاً: **`install.bat`** يحاول تلقائياً:
  1. استخدام Python من PATH أو **`py -3`** أو مسارات شائعة.
  2. إن تعذّر ذلك، تثبيت **Python 3.12** عبر **`winget`** عند التوفر.
  3. إنشاء **`venv`** وتثبيت **`requirements.txt`** (لوحة الويب وقاعدة البيانات).
  4. إنشاء **`logs`** و **`list`** و **`data`** و **`data\backups`**.
  5. عند إنشاء **`.env`** جديد من **`.env.example`**، أو عند اختيار **Y** لإعادة الإعداد إن وُجد `.env` مسبقاً، يشغّل **`install.bat`** أسئلة تفاعلية (سكربت **`scripts/write_install_env.py`**) لكتابة **`DASHBOARD_PASSWORD`** والمتغيرات الاختيارية (`DB_*` للقاعدة، `DASHBOARD_SECRET`، العنوان والمنفذ).

إذا لم يكن **winget** متوفراً وليس لديك Python، ثبّت Python من [python.org](https://www.python.org/downloads/) مع **Add python.exe to PATH** ثم أعد تشغيل **`install.bat`**.

---

## بعد التثبيت (مسار موصى به)

1. **`install.bat`** يكون قد سألك عن **`.env`** (أو أعد تشغيله واختر **Y** عند سؤال إعادة الإعداد). المتغيرات المتعلقة باللوحة فقط؛ **توكن البوت** و**المعرف الأساسي** والشاتات والردود تُضبط من **لوحة التحكم** بعد التشغيل.
2. **تشغيل / إيقاف اللوحة (في الخلفية):** **`run.bat`** — إن كانت اللوحة تعمل يُوقفها، وإن كانت متوقفة يشغّلها في الخلفية (`run_dashboard.py toggle`).
3. **تشغيل اللوحة في نفس النافذة (أمامي):** `venv\Scripts\python.exe run_dashboard.py start` (أو على لينكس: `./venv/bin/python3 run_dashboard.py start`).
4. افتح المتصفح على `http://127.0.0.1` (المنفذ الافتراضي **80** عندما يكون `DASHBOARD_PORT` فارغاً؛ أو استخدم `DASHBOARD_HOST` / `DASHBOARD_PORT` من `.env`)، سجّل الدخول، اضبط **البوتات** و**المحادثات** و**الردود**، ثم **شغّل البوت** من شريط التنقل أعلى الصفحة.
5. للمطورين فقط: لتشغيل **البوت وحده** بدون واجهة لوحة: `venv\Scripts\python.exe main.py` — لا يُستخدم كمسار يومي؛ المسار العادي هو اللوحة ثم «تشغيل البوت» من الواجهة.

**إلغاء التثبيت:** `uninstall.bat` ينشئ نسخة احتياطية إلزامية تحت `data\backups\` قبل الحذف.

---

## الطريقة 1: تحميل يدوي من المتصفح

1. [أرشيف الفرع `main` (ZIP)](https://github.com/mPhpMaster/saherbot/archive/refs/heads/main.zip) أو من صفحة الريبو: **Code → Download ZIP**.
2. فك الضغط؛ غالباً يظهر مجلد **`saherbot-main`**.
3. ادخل المجلد وشغّل **`install.bat`** وأجب عن أسئلة **`.env`** إن ظهرت.
4. اتبع قسم **«بعد التثبيت»** أعلاه.

---

## الطريقة 2: أمر PowerShell (نسخ ولصق)

```powershell
cd $env:USERPROFILE\Desktop
$url = 'https://github.com/mPhpMaster/saherbot/archive/refs/heads/main.zip'
$zip = Join-Path $env:TEMP 'saherbot-main.zip'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
Expand-Archive -Path $zip -DestinationPath (Get-Location) -Force
Remove-Item $zip
Set-Location .\saherbot-main
.\install.bat
```

ثم اتبع **«بعد التثبيت»**. إن وُجد `saherbot-main` مسبقاً، احذفه أو غيّر مجلد العمل قبل `Expand-Archive`.

---

## الطريقة 3: `download-and-install.bat`

1. ضع **`download-and-install.bat`** في المجلد الذي تريد أن يُنشأ فيه **`saherbot-main`** بجانبه.
2. شغّله بالنقر المزدوج: يحمّل ZIP، يفك إلى **`saherbot-main`**، يشغّل **`install.bat`** (مع أسئلة **`.env`** عند الحاجة).
3. ادخل **`saherbot-main`** ثم **`run.bat`** لتشغيل اللوحة في الخلفية، أو شغّل **`venv\Scripts\python.exe run_dashboard.py start`** للأمامي، ثم اضبط البوت من الواجهة.

---

## اختياري: سطح المكتب وتسمية مجلد مخصصة

سكربتات **`download-saherbot.bat`** و **`download-saherbot.ps1`** تحمّل نفس الأرشيف إلى سطح المكتب باسم مجلد تختاره (افتراضياً **`saherbot`**) وتشغّل **`install.bat`**. بعد الانتهاء: **`run.bat`** للتبديل في الخلفية، أو **`venv\Scripts\python.exe run_dashboard.py start`** للأمامي، ثم الإعداد من اللوحة.

---

## مع Git (Windows و Linux/macOS)

```powershell
git clone https://github.com/mPhpMaster/saherbot.git
cd saherbot
```

- **Windows:** `.\install.bat` ثم **`run.bat`** للتبديل، أو **`venv\Scripts\python.exe run_dashboard.py start`** للأمامي.
- **Linux/macOS:** `./install.sh` (يضبط **`chmod +x run.sh`** عند الإمكان)، ثم **`./run.sh`** للتبديل، أو `./venv/bin/python3 run_dashboard.py start` للأمامي.

---

## روابط مباشرة

| الغرض | الرابط |
|--------|--------|
| أرشيف الفرع `main` (ZIP) | [archive/refs/heads/main.zip](https://github.com/mPhpMaster/saherbot/archive/refs/heads/main.zip) |
| صفحة المستودع | [github.com/mPhpMaster/saherbot](https://github.com/mPhpMaster/saherbot) |
