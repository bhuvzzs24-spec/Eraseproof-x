FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY eraseproof ./eraseproof
COPY migrations ./migrations
RUN pip install --no-cache-dir -c requirements.lock . && useradd --uid 10001 --create-home lab
USER lab
CMD ["uvicorn", "eraseproof.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
