FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/hermes-src

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/repo-requirements.txt
COPY services/hermes-runtime/requirements.txt /tmp/runtime-requirements.txt
RUN pip install --no-cache-dir -r /tmp/repo-requirements.txt && \
    pip install --no-cache-dir -r /tmp/runtime-requirements.txt

COPY . /opt/hermes-src

COPY services/hermes-runtime/app ./app

EXPOSE 8081
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081"]
