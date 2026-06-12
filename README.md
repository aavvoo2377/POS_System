[README.md](https://github.com/user-attachments/files/28881809/README.md)
# نظام البيع المتكامل — POS System

نظام نقاط بيع متكامل يعمل بدون إنترنت، مع دعم كامل للغة العربية والطباعة الحرارية.

## المميزات

- **واجهة عربية** بالكامل، تصميم عصري (CustomTkinter)
- **البيع** — إضافة المنتجات، البحث بالباركود، إدارة السلة
- **المنتجات** — إدارة المخزون، الباركود، الأسعار
- **الملصقات** — طباعة ملصقات باركود (Code128) على طابعات لاصقة
- **الفواتير الحرارية** — طباعة فواتير استلام وتسليم (80/58mm)
- **التقارير** — تقارير يومية وشهرية مع تصدير PDF
- **الترخيص** — تفعيل البرنامج عبر فلاشة USB بتشفير HMAC-SHA256
- **الإعدادات** — ضبط اسم المتجر، الضريبة، قفل الدخول، قوالب الفواتير

## التقنيات

- Python 3.13+ · CustomTkinter · SQLite · Pillow
- win32print / win32ui (طباعة حرارية)
- python-barcode · qrcode · arabic_reshaper · python-bidi
- PyInstaller (تعبئة EXE)

## التشغيل

### تشغيل الكود المصدري

```bash
pip install -r requirements.txt
python main.py
```

### بناء نسخة EXE

```bash
python build_exe.py
# الملف الناتج: dist/POS_System.exe
```

### بناء أداة الترخيص

```bash
build_license_tool.bat
# الملف الناتج: dist_license/LicenseGenerator.exe
```

## هيكل المشروع

```
pos_system/
├── main.py                # نقطة الدخول
├── database.py            # قاعدة البيانات والاستعلامات
├── utils.py               # أدوات عامة + ملصقات الباركود
├── invoice_printer.py     # طباعة الفواتير الحرارية
├── invoice_config.py      # إعدادات قوالب الفواتير
├── license_utils.py       # تفعيل الترخيص (USB + HMAC)
├── license_gui.py         # واجهة توليد مفاتيح التفعيل
├── generate_license.py    # أداة CLI لتوليد الترخيص
├── build_exe.py           # سكربت بناء EXE
├── config/                # إعدادات
├── assets/                # صور وأيقونات
└── ui/
    ├── main_window.py     # النافذة الرئيسية
    ├── pos_view.py        # واجهة البيع
    ├── product_dialog.py  # إضافة/تعديل المنتجات
    ├── product_manager.py # إدارة المنتجات
    ├── reports_view.py    # التقارير
    ├── settings_view.py   # الإعدادات
    ├── invoice_template_editor.py  # محرر قالب الفاتورة
    ├── print_dialog.py    # حوار الطباعة
    ├── quantity_dialog.py # حوار الكمية
    └── date_picker.py     # منتقي التاريخ
```

## الترخيص

هذا المشروع يستخدم نظام تفعيل عبر فلاشة USB:
1. تُنشئ مفتاح ترخيص باستخدام `LicenseGenerator.exe`
2. تُحفظ على فلاشة USB
3. البرنامج يقرأ الفلاشة ويفعّل نفسه تلقائياً
4. كل مفتاح يستخدم لمرة واحدة فقط

## متطلبات التشغيل

- Windows 10/11
- طابعة حرارية (اختياري — للفواتير والملصقات)
- قارئ باركود (اختياري)
