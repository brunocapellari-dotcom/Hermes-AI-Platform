FROM python:3.14.8-slim-trixie@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system hermes \
    && adduser --system --ingroup hermes hermes
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
RUN mkdir -p /data && chown -R hermes:hermes /data
USER hermes
EXPOSE 8080
CMD ["uvicorn", "hermes.asgi:app", "--host", "0.0.0.0", "--port", "8080"]
