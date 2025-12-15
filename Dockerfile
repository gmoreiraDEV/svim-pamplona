FROM python:3.13.1-slim

# Evitar buffering em logs
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
 && apt-get upgrade -y \
 && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    build-essential \
 && rm -rf /var/lib/apt/lists/*


# Copia requirements e instala deps
COPY ./requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código do agente
COPY app/ .

# Garante que /app está no PYTHONPATH
ENV PYTHONPATH=/app

# Entry-point padrão (pode ser sobrescrito pelo Kestra se quiser)
CMD ["python", "-m", "app.agent.main"]
