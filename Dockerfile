FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY config ./config
COPY prompts ./prompts
RUN pip install --no-cache-dir .
ENV PORT=8080
CMD ["sh", "-c", "uvicorn agent.main:app --host 0.0.0.0 --port ${PORT}"]
