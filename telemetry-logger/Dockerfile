FROM python:3.11-slim
COPY ./code /code
WORKDIR /code
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "telemetry-logger.py"]