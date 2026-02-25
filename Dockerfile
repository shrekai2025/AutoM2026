FROM python:3.10-slim-bookworm

# Install system dependencies needed for Playwright and other native python packages
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y \
    curl \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install python deps
COPY requirements.txt /app/
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r requirements.txt

# Install Playwright browser binaries (Chromium only for ETF flow crawler)
RUN playwright install chromium --with-deps

# Copy application files
COPY . /app/

# Environment configurations
ENV PYTHONUNBUFFERED=1
ENV TZ="Asia/Shanghai"

# Expose port (default in settings is 8080)
EXPOSE 8080

# Command to run the application
CMD ["python", "main.py"]
