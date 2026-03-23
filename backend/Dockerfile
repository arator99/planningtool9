FROM python:3.12-slim

WORKDIR /app

# Installeer dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopieer broncode
COPY backend/ .

# ── Tailwind CLI — statisch binair, geen npm/node nodig ──
# Pin op v3.x (v4 heeft ander config-formaat)
RUN apt-get update && apt-get install -y --no-install-recommends curl postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && curl -sL https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-linux-x64 \
         -o /usr/local/bin/tailwindcss \
    && chmod +x /usr/local/bin/tailwindcss \
    && tailwindcss \
         -c tailwind.config.js \
         -i ./static/css/input.css \
         -o ./static/css/output.css \
         --minify \
    && echo "Tailwind CSS gebouwd: $(wc -c < ./static/css/output.css) bytes"

# Poort
EXPOSE 8000

# Start: hot-reload in development, meerdere workers in productie
CMD sh -c 'if [ "$OMGEVING" = "development" ]; then \
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload; \
  else \
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2; \
  fi'
