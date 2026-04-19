FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir -e .

EXPOSE 47201
CMD ["uvicorn", "inference_backend.main:app", "--host", "0.0.0.0", "--port", "47201"]
