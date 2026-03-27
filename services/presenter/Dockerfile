FROM python:3.12-slim

WORKDIR /app

COPY xeter/pyproject.toml xeter/pyproject.toml
RUN pip install --no-cache-dir -e xeter/

COPY xeter/ xeter/

CMD ["uvicorn", "xeter.services.presenter.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
