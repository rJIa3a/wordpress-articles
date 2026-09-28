FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    INTERLINKER_DB=/data/interlinker.sqlite3

WORKDIR /app
COPY requirements-service.txt ./requirements-service.txt
RUN pip install --no-cache-dir -r requirements-service.txt
COPY interlinker ./interlinker
COPY city_benchmark ./city_benchmark
COPY tools/docker_init_data.py ./tools/docker_init_data.py
COPY run.py ./run.py

RUN useradd --system --uid 10001 --create-home app \
    && mkdir -p /data \
    && chown -R app:app /app /data
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["python", "run.py"]
