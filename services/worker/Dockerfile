FROM python:3.12-slim
WORKDIR /app

# Install xeter package and its dependencies
COPY xeter/ xeter/
RUN pip install --no-cache-dir -e xeter/

# Worker-specific deps: embeddings, PostgreSQL, S3
RUN pip install --no-cache-dir sentence-transformers psycopg2-binary boto3

# Pre-bake the sentence-transformers model into the image layer.
# This avoids an 80 MB download at container startup on first span.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy Docker entry point
COPY services/worker/ services/worker/

CMD ["python", "services/worker/main.py"]
