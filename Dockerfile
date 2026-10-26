FROM python:3.10-slim

# Hugging Face Spaces requires a non-root user with UID 1000
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860

WORKDIR $HOME/app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY --chown=user:user requirements.txt $HOME/app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy all application files with proper ownership
COPY --chown=user:user . $HOME/app

# Ensure writable directories for uploads and SQLite database
RUN mkdir -p $HOME/app/uploads $HOME/app/data && \
    chmod -R 777 $HOME/app/uploads

# Switch to non-root user
USER user

# Hugging Face Spaces listens on port 7860
EXPOSE 7860

# Production WSGI server using Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:7860", "--workers", "2", "--threads", "4", "--timeout", "120", "app:app"]
