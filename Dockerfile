FROM python:3.12-slim

WORKDIR /app

# ===== بخش اضافه شده برای رفع مشکل اینترنت =====
RUN pip config set global.index-url https://mirror-pypi.runflare.com/simple/ && \
    pip config set global.trusted-host mirror-pypi.runflare.com
# ============================================

# کپی کردن requirements.txt و نصب وابستگی‌ها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی کردن فایل‌های اصلی پروژه
COPY app.py .
COPY celery_app.py .
COPY tasks.py .
COPY database.py .
COPY image_processor.py .
COPY minio_client.py .
COPY crud.py .
COPY .env .

# کپی کردن پوشه frontend (در صورت وجود)
COPY frontend ./frontend

# ایجاد پوشه uploads
RUN mkdir -p uploads/temp-mean-io uploads/final-bucket

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]