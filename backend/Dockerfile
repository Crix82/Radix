FROM python:3.12-slim

WORKDIR /app

# Tesseract (OCR, SPEC §2 langs ita+eng+deu) and the shared libs Docling/OpenCV need.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-ita \
        tesseract-ocr-eng \
        tesseract-ocr-deu \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
COPY worker ./worker
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --no-cache-dir .

# Pre-fetch Docling layout/table models at build time so runtime makes no external
# calls (SPEC §9). Models are baked into the image cache.
RUN docling-tools models download

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
