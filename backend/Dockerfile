FROM python:3.12-slim

WORKDIR /app

# Installeer dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopieer broncode (CHANGELOG.md zit al in backend/)
COPY backend/ .

# Poort
EXPOSE 8000

# Start: hot-reload in development, meerdere workers zonder reload in productie
CMD sh -c 'if [ "$OMGEVING" = "development" ]; then \
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload; \
  else \
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2; \
  fi'
