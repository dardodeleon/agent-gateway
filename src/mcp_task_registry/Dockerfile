FROM python:3.12-slim

WORKDIR /app

COPY mcp_task_registry/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared/
COPY mcp_task_registry/ /app/

EXPOSE 8001

CMD ["python", "server.py"]
