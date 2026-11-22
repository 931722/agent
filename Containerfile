FROM docker.io/library/python:3.14-slim
WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY tests ./tests
COPY pyproject.toml ./
RUN useradd --create-home --uid 10001 kitchen && mkdir -p /app/data && chown kitchen:kitchen /app/data
USER kitchen
ENV PYTHONUNBUFFERED=1 DB_PATH=/app/data/kitchen.sqlite3 AGENT_MODE=ollama OLLAMA_BASE_URL=http://host.containers.internal:11434 OLLAMA_MODEL=qwen3:4b
EXPOSE 8000
CMD ["python", "-m", "app", "serve", "--host", "0.0.0.0", "--port", "8000"]
