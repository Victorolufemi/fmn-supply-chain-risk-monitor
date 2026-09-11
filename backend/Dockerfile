# Build context is the REPOSITORY ROOT, not backend/, because the image needs
# both the application and data/project1_supply_chain_demand.csv:
#
#   docker build -f backend/Dockerfile -t fmn-supply-chain-api .
#   docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-... fmn-supply-chain-api
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so application edits do not invalidate the wheel layer.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY data/ ./data/

# Train at build time. The artifact bundle pickles fitted scikit-learn objects,
# which are sensitive to library versions, so building it inside the image with
# the exact pinned versions removes a whole class of load-time failures. It also
# means the first request after a deploy is served from a warm model rather than
# waiting on a cold train.
WORKDIR /app/backend
RUN python -m app.ml.training

EXPOSE 8000

# Render injects $PORT; default to 8000 for local runs. Binding 0.0.0.0 is
# required — a container listening on 127.0.0.1 is unreachable from outside.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
