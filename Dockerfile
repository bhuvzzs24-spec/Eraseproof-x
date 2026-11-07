FROM python:3.12-slim@sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54
WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY eraseproof ./eraseproof
COPY migrations ./migrations
COPY policies ./policies
COPY research/phase-4/config ./research/phase-4/config
RUN pip install --no-cache-dir -c requirements.lock . && useradd --uid 10001 --create-home lab
USER lab
CMD ["uvicorn", "eraseproof.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
