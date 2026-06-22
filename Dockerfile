FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    TZ=Europe/Bucharest \
    PUBLIC_HOSTS=192.168.1.142,nutrition-mcp \
    HOST=0.0.0.0 \
    PORT=8765

WORKDIR /app

RUN addgroup --system nutrition && adduser --system --ingroup nutrition nutrition

COPY pyproject.toml README.md ./
COPY app ./app

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir .

RUN mkdir -p /data/exports && chown -R nutrition:nutrition /data /app

USER nutrition

EXPOSE 8765

CMD ["python", "-m", "app.main"]
