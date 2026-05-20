FROM python:3.12-slim
WORKDIR /app
ENV PYTHONPATH=/app

# Install xeter package (no ML deps needed — embedder is a separate service)
COPY xeter/ xeter/
RUN pip install --no-cache-dir -e xeter/

# Worker-specific deps: PostgreSQL, S3, Redis, spaCy NLP
RUN pip install --no-cache-dir psycopg2-binary boto3 redis httpx spacy jsonschema tiktoken rapidfuzz && \
    python -m spacy download en_core_web_md

# Copy Docker entry point
COPY services/worker/ services/worker/

CMD ["python", "services/worker/main.py"]
