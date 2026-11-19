# Build the React dashboard once, then serve it and FastAPI from the same origin.
FROM node:22-slim AS frontend
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY backend/app backend/app
COPY data data
RUN python -m pip install --no-cache-dir .
COPY --from=frontend /ui/dist frontend/dist
USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
