FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app

COPY xeter/pyproject.toml xeter/pyproject.toml
RUN pip install --no-cache-dir -e xeter/

COPY xeter/ xeter/

CMD ["uvicorn", "xeter.services.diagnosticer.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
