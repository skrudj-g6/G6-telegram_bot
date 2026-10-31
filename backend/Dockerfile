FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Не root. Каталог чеков создаётся заранее с нужным владельцем: именованный том Docker
# наследует его при первом монтировании, иначе appuser не смог бы писать файлы.
RUN useradd --create-home appuser \
    && mkdir -p /data/receipts \
    && chown -R appuser:appuser /data
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
