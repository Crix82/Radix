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

# Dependencies first, from the pinned lockfile: the layer is cached across code changes, and
# the resolution can't drift between a verification run and a customer install.
# The BuildKit cache mount (rather than --no-cache-dir) keeps the ~2.5 GB of wheels — torch and
# the CUDA stack — outside the image but on disk, so a build interrupted by one bad download
# resumes instead of re-fetching everything. Nothing from the mount lands in the image layer.
COPY requirements.lock ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps -r requirements.lock

COPY pyproject.toml ./
COPY app ./app
COPY worker ./worker
COPY migrations ./migrations
COPY alembic.ini ./

RUN pip install --no-cache-dir --no-deps .

# Pre-fetch the models at build time so runtime makes no external calls (SPEC §9):
# Docling layout/table models and the bge-m3 embedding model, baked into the image cache.
#
# Warm the models through the service's own converters instead of `docling-tools models
# download`. Two reasons, both found by parsing a fixture under `--network none`:
#   1. The CLI writes to /root/.cache/docling/models, but docling's LayoutModel resolves via
#      snapshot_download into the HuggingFace cache. The M6 image therefore fetched the layout
#      model from the Hub on the first document — SPEC §9 promises no runtime external calls,
#      and an air-gapped install broke on first use. Verified against the M6 image itself.
#   2. The CLI's default set includes the rapidocr/easyocr engines Radix never uses (parsing is
#      Tesseract via TesseractCliOcrOptions) and the VLM checkpoints; rapidocr's Chinese models
#      come from modelscope.cn, which timed out and failed a build here. install.sh builds on
#      the customer's machine, so that host sat on every install's critical path.
# Warming the real converters downloads exactly what the runtime resolves — no more, no less.
RUN python -c "from app.services.parsing import warm_models; warm_models()"
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
