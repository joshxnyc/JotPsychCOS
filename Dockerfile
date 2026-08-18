FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    DB_PATH=/data/app.db \
    STATE_DIR=/data/state

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY machine/ ./machine/
COPY app/ ./app/
COPY config/ ./config/
COPY inbox/ ./inbox/
COPY assets/ ./assets/
COPY tools/ ./tools/

# The volume is mounted at /data. Everything the machine must not lose lives
# there: the database and its registry snapshot.
RUN mkdir -p /data/state /srv/out

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/healthz')"

CMD ["uvicorn", "app.main:api", "--host", "0.0.0.0", "--port", "8080"]
