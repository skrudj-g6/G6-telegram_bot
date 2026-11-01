FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Не root. У бота нет доступа к БД: только backend API (ТЗ §3, D-2).
RUN useradd --create-home appuser
USER appuser

CMD ["python", "-m", "botapp.main"]
