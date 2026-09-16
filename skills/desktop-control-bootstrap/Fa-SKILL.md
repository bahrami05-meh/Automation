---
name: desktop-control-bootstrap
description: Run Jack's required local mouse-motion bootstrap before taking control of the user's Windows desktop. Use whenever the user explicitly asks Jack to control the desktop, mouse, keyboard, or a Windows application.
metadata:
  short-description: Required safe bootstrap for Jack desktop control
---

پروزه اتوماسیون بورسی

# راه‌اندازی اجباری کنترل دسکتاپ جک

## زمان استفاده

هرگاه کاربر صریحاً از جک بخواهد کنترل دسکتاپ، ماوس، کیبورد یا یک برنامهٔ ویندوزی را به دست بگیرد، این اسکیل باید پیش از نخستین اقدام ورودی روی سیستم اجرا شود.

## گام اجباری نخست

پیش از هر کلیک، درگ، تایپ یا فشردن کلید، اسکریپت زیر را با مفسر پایتون پیکربندی‌شدهٔ پروژه اجرا کن:

```powershell
F:\Automasion\.venv\Scripts\python.exe F:\Automasion\mouse_motion_test.py --duration 15
```

این اسکریپت فقط نشانگر را حرکت می‌دهد، کلیک یا ورود متن انجام نمی‌دهد و در پایان نشانگر را به محل شروع برمی‌گرداند.

## شرط ادامه

- فقط پس از پایان موفق اسکریپت، کنترل دسکتاپ را ادامه بده.
- اگر اسکریپت خطا داد، کنترل ورودی دسکتاپ را آغاز نکن؛ خطا را شفاف گزارش کن.
- اجرای موفق برای هر درخواست مستقل کنترل دسکتاپ لازم است؛ در طول همان درخواست، یک اجرا کافی است.
- این اسکیل مجوز اقدام پرریسک ایجاد نمی‌کند. برای ورود رمز، CAPTCHA، ارسال فرم، تغییر تنظیمات امنیتی یا اقدام مالی، قواعد تأیید و واگذاری به کاربر همچنان برقرار است.
