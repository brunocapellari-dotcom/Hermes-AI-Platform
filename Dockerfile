FROM python:3.14.7-slim-trixie@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS runtime
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
