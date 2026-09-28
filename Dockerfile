FROM python:3.12-slim
WORKDIR /service
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ANONYMIZED_TELEMETRY=False
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY opsdesk opsdesk
COPY knowledge knowledge
COPY skills skills
COPY web web
RUN useradd --uid 10001 --create-home opsdesk && mkdir -p var && chown -R opsdesk:opsdesk /service
USER opsdesk
CMD ["uvicorn", "opsdesk.main:app", "--host", "0.0.0.0", "--port", "8085"]
