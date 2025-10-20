FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Include both server and chart generator
COPY weather_server.py chart.py .

EXPOSE 5000

CMD ["python", "weather_server.py"]
