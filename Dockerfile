FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app

RUN pip install . \
    && groupadd --system --gid 10001 monitor \
    && useradd --system --uid 10001 --gid monitor --no-create-home monitor \
    && mkdir -p /data \
    && chown -R monitor:monitor /app /data

USER 10001:10001

EXPOSE 8000

CMD ["python", "-m", "app"]
