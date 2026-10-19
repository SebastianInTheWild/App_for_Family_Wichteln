FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV WICHTEL_DATA_DIR=/data PYTHONDONTWRITEBYTECODE=1
VOLUME /data
EXPOSE 8080
CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "1", "--timeout", "180", "app:app"]
