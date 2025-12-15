FROM python:3.13.1-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip \
 && python -m pip install --no-cache-dir -r requirements.txt

# ✅ importante: mantém a pasta app como pacote "app"
COPY app ./app

ENV PYTHONPATH=/app

CMD ["python", "-m", "app.agent.main"]
