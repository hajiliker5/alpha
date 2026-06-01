# Dockerfile (Lightweight Reverse Proxy Builder)
FROM python:3.9-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# کپی کردن لیست نیازمندی‌های بسیار سبک پروکسی رانفلر
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی کردن فایل اصلی برنامه پروکسی رانفلر
COPY app.py .

# باز کردن پورت پیش‌فرض برای رانفلر
EXPOSE 7860

# اجرای وب‌سرور با عملکرد و ظرفیت بالا جهت هندل کردن درخواست‌های استریم ویدیو و وب‌سوکت
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "4", "--limit-concurrency", "2000"]
