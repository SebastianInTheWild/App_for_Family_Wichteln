FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV WICHTEL_DATA_DIR=/data PYTHONDONTWRITEBYTECODE=1
VOLUME /data
EXPOSE 8080
# Ein Prozess (Zeitplan-Thread läuft nur einmal), mehrere Threads: leere Browser-
# Verbindungen und langsamer Mailversand blockieren so keine anderen Anfragen.
CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "1", "-k", "gthread", "--threads", "8", "--timeout", "180", "app:app"]
