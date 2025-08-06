# Use official Python base image
FROM python:3.11-slim

# Install system dependencies needed by pyzbar (zbar)
RUN apt-get update && apt-get install -y \
    libzbar0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install Python packages
RUN pip install --upgrade pip && pip install -r requirements.txt

# Expose port (Render uses this to connect to your app)
EXPOSE 10000

# Start the app with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]
