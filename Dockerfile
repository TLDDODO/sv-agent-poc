FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install dependencies first so this layer caches across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY . .

EXPOSE 8000
EXPOSE 8765

# DEEPSEEK_API_KEY is supplied at runtime (never baked into the image):
#   docker run -e DEEPSEEK_API_KEY=sk-... -p 8000:8000 <image>
# The same image also runs the MCP server (see docker-compose.yml, service "mcp"); its
# command overrides this default CMD.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
