FROM python:3.13.1-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip \
 && python -m pip install --no-cache-dir -r requirements.txt

# ✅ copia a pasta app como subpasta /app/app
COPY app ./app

# ✅ opcional, mas ajuda em qualquer runner
ENV PYTHONPATH=/app

CMD ["python", "-m", "app.agent.main"]
