# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    ghostscript \
    unpaper \
    qpdf \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    libtiff-dev \
    liblcms2-dev \
    libwebp-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

# Expose Flask port
EXPOSE 5000

# Entrypoint for production (use gunicorn)
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000", "--timeout", "120"] 