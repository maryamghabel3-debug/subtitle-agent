# فونت وزیرمتن (Vazirmatn)

زیرنویس‌های فارسی با فونت **وزیرمتن** رندر می‌شوند — فونت آزاد و خوانای فارسی
از پروژه [rastikerdar/vazirmatn](https://github.com/rastikerdar/vazirmatn)
با مجوز SIL Open Font License 1.1 (فایل `OFL.txt`).

دو فایل `Vazirmatn-Regular.ttf` و `Vazirmatn-Bold.ttf` همراه ریپو هستند.
اگر حذف شده بودند:

```bash
python scripts/download_font.py
```

ffmpeg هنگام چسباندن زیرنویس، با گزینه `fontsdir` همین پوشه را می‌خواند،
پس لازم نیست فونت را روی سیستم نصب کنید. برای استفاده از فونت دیگری
(مثلاً یک فونت نستعلیق) فایلش را اینجا بگذارید و `font_name` را در
کانفیگ برابر نام داخلی همان فونت کنید.
