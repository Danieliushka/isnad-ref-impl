FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir -e .

# Expose API port
EXPOSE 8000

# Default: run the REST API
CMD ["python", "api.py"]
