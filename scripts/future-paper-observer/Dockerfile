FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY scripts/future_altcoin_paper.py scripts/future_btc5m_conditions.py /app/
USER 10001:10001
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
CMD ["python", "future_altcoin_paper.py", "--state-dir", "/state"]
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=3 CMD python -c "import json,urllib.request; assert json.load(urllib.request.urlopen('http://127.0.0.1:8777/health',timeout=3))['fresh']"
