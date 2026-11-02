# Scraper Service Dockerfile
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies for Playwright Chromium
# Manually specifying all dependencies to avoid playwright install-deps issues
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    # Font packages (using updated names for Debian Trixie)
    fonts-liberation \
    fonts-unifont \
    # Browser dependencies
    libasound2t64 \
    libatk-bridge2.0-0t64 \
    libatk1.0-0t64 \
    libatspi2.0-0t64 \
    libcairo2 \
    libcups2t64 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0t64 \
    libgtk-3-0t64 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libwayland-client0 \
    libx11-6 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    # Additional utilities
    libgbm1 \
    libenchant-2-2 \
    libsecret-1-0 \
    libhyphen0 \
    libmanette-0.2-0 \
    libflite1 \
    libgstreamer1.0-0 \
    libgstreamer-plugins-base1.0-0 \
    libgstreamer-plugins-bad1.0-0 \
    libegl1 \
    libopenjp2-7 \
    libwebpdemux2 \
    libharfbuzz-icu0 \
    libgles2 \
    gstreamer1.0-libav \
    libvpx9 \
    libwoff1 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user FIRST
RUN useradd -m -u 1000 scraper && \
    chown -R scraper:scraper /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir psycopg2-binary

# Switch to scraper user BEFORE installing Playwright browsers
USER scraper

# Install Playwright Chromium browser as scraper user
RUN playwright install chromium

# Copy scraper files
COPY --chown=scraper:scraper run_scraper.py .
COPY --chown=scraper:scraper scraper.py .
COPY --chown=scraper:scraper run_vtinfo_scraper.py .
COPY --chown=scraper:scraper vtinfo_scraper.py .
COPY --chown=scraper:scraper database.py .

# Create directory for screenshots
RUN mkdir -p /app/screenshots

# Default command (can be overridden)
CMD ["python", "run_scraper.py"]
