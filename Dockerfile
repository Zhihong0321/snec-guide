# SNEC 2026 Guide — production image for Railway (Docker build)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

COPY web/ ./web/
COPY expo_map_guide.md sections_analysis.md ./
COPY floor_plans/ ./floor_plans/
COPY official_commercial_guide.pdf official_2026_venue_guide.pdf ./

RUN mkdir -p uploads

EXPOSE 8080

# Railway injects PORT; bind all interfaces for the platform proxy
CMD ["sh", "-c", "uvicorn web.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
