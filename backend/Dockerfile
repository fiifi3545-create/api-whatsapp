FROM python:3.10-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# Shell form so $PORT expands. Render injects PORT at runtime; falls back to
# 8080 for local `docker run`. --timeout 120 accommodates Gemini LLM calls
# that can take 20-40s under load.
CMD gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 2 --threads 4 --timeout 120 wsgi:app
