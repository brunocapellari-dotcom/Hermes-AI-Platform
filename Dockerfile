FROM python:3.12.14-slim-trixie@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea AS runtime
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
USER hermes
EXPOSE 8080
CMD ["uvicorn", "hermes.asgi:app", "--host", "0.0.0.0", "--port", "8080"]
