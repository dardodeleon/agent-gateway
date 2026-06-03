FROM python:3.12-slim

WORKDIR /app

COPY mcp_agent_gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared/
COPY mcp_agent_gateway/ /app/

EXPOSE 8003

CMD ["python", "server.py"]
