FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN adduser --disabled-password --no-create-home botuser \
    && chown -R botuser:botuser /app
USER botuser

CMD ["python", "-m", "bot.main"]
