FROM python:3.11-slim

WORKDIR /app

# Install required packages including fonts for Hindi support
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libmupdf-dev \
    mupdf \
    mupdf-tools \
    fonts-noto-cjk \
    fonts-noto-cjk-extra \
    fonts-noto \
    fonts-freefont-ttf \
    locales \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set up locale for Hindi support
RUN sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && \
    sed -i -e 's/# hi_IN UTF-8/hi_IN UTF-8/' /etc/locale.gen && \
    locale-gen
ENV LANG hi_IN.UTF-8
ENV LC_ALL hi_IN.UTF-8

# Install Python dependencies directly
RUN pip install --no-cache-dir python-telegram-bot==13.15 flask==2.3.3 reportlab==4.0.4 gunicorn==21.2.0 psycopg2-binary==2.9.7 python-dotenv==1.0.0

# Install PDF libraries explicitly
RUN pip install --no-cache-dir PyMuPDF==1.22.5 PyPDF2==3.0.1

# Copy the application code
COPY . .

# Expose the port for health checks
EXPOSE 8080

# Start the bot
CMD ["python", "healthcheck.py"]
