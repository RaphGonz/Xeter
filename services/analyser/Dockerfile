FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi "uvicorn[standard]"

COPY services/analyser/ services/analyser/

CMD ["uvicorn", "services.analyser.main:app", "--host", "0.0.0.0", "--port", "4318"]
