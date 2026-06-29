FROM python:3.12-slim

WORKDIR /app

# Install C build toolchain — required for biopython on ARM64 (WSL2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app

CMD ["python", "worker.py"]
