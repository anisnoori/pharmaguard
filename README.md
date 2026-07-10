# PharmaGuard AI — نسخه Production Final v0.12.0

سامانه هوشمند پایش زنجیره تأمین دارو مبتنی بر هوش مصنوعی برای بیمارستان‌ها، داروخانه‌ها و سازمان‌های درمانی.

## اجرای محلی

```bash
cd pharmaguard_ai_foundation
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
streamlit run app.py
```

## ادمین اصلی

قبل از دیپلوی، متغیرهای زیر را در فایل `.env` یا Secrets پلتفرم قرار دهید:

```env
PHARMAGUARD_ADMIN_EMAIL=anisgulnoori93@gmail.com
PHARMAGUARD_ADMIN_PASSWORD=رمز_قوی_خودت
PHARMAGUARD_ADMIN_NAME=Anisgul Noori
PHARMAGUARD_DEFAULT_THEME=light
APP_ENV=production
```

اگر دیتابیس قبلاً ساخته شده باشد، برای ساخت دوباره ادمین اصلی باید `database/pharmaguard.db` را حذف کنید یا از پنل مدیریت، کاربر خود را administrator کنید.

## مسیر استفاده واقعی برای گرفتن داده از داروخانه/بیمارستان

1. ادمین اصلی وارد سامانه می‌شود.
2. در «مدیریت سامانه»، بیمارستان یا داروخانه را با استان، شهر، آدرس، شماره تماس و مجوز ثبت می‌کند.
3. برای هر سازمان، کاربر مسئول با نقش مناسب ساخته یا درخواست ثبت‌نام او تأیید می‌شود.
4. داروخانه/بیمارستان فایل موجودی را از بخش «ورود داده» وارد می‌کند.
5. سیستم نام دارو را required می‌داند و سایر ستون‌ها مانند موجودی، بچ، انقضا، تأمین‌کننده و مصرف ماهانه optional هستند.
6. بعد از ورود داده، هشدارها، پیش‌بینی کمبود، تداخل دارویی، اسکن دارو و گزارش‌های مدیریتی قابل استفاده هستند.

## حفظ داده در نسخه‌های بعدی

برای انتقال داده‌ها به نسخه جدید، این مسیرها را نگه دارید:

- `database/pharmaguard.db`
- `uploads/`
- `reports/`
- `logs/`

## دیپلوی

در Hugging Face / Streamlit Cloud / Replit، متغیرهای `.env.example` را در بخش Secrets قرار دهید و سپس دستور زیر را اجرا کنید:

```bash
streamlit run app.py
```

## فایل‌های نمونه برای دریافت داده

- `samples/drugstore_minimum_template.csv` برای حداقل داده: نام دارو و موجودی
- `samples/drugstore_full_template.csv` برای داده کامل‌تر: بچ، انقضا، تأمین‌کننده و مصرف ماهانه
- `docs/DRUGSTORE_DATA_COLLECTION_GUIDE.md` راهنمای گرفتن فایل از داروخانه یا بیمارستان

در رابط کاربری، عبارت‌های دمو و فازهای توسعه حذف شده‌اند و مسیر ارائه روی استفاده واقعی سازمانی تنظیم شده است.
