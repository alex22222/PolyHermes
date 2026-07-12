FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    xvfb \
    fluxbox \
    x11vnc \
    novnc \
    websockify \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium

# Copy application code and the optional local-only noVNC launcher.
COPY *.py bridge-entrypoint.sh ./
RUN chmod +x /app/bridge-entrypoint.sh

# Create profile directory
RUN mkdir -p /app/browser_profile

EXPOSE 8080
EXPOSE 6080

CMD ["/app/bridge-entrypoint.sh"]
