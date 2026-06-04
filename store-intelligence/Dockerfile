FROM python:3.11-slim

WORKDIR /store-intelligence

# Install curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy only the code files
COPY app/ ./app/

# Install only API dependencies (No heavy ML/CV packages like torch or ultralytics needed for API service)
RUN pip install --no-cache-dir \
    fastapi==0.110.0 \
    uvicorn==0.28.0 \
    sqlalchemy==2.0.28 \
    pydantic==2.6.4 \
    pandas==2.2.1 \
    numpy==1.26.4

# Expose FastAPI port
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
