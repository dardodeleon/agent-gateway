FROM python:3.12-slim

WORKDIR /app

COPY dispatcher/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared/
COPY dispatcher/ /app/

# Volumes agents/, tools/, skills/ and models.yml are mounted via docker-compose

CMD ["python", "main.py"]
