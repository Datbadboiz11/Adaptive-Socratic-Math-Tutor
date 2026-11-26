FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
COPY backend/requirements-rag.txt ./requirements-rag.txt
ARG INSTALL_RAG=false
RUN if [ "$INSTALL_RAG" = "true" ]; then pip install --no-cache-dir -r requirements-rag.txt; else pip install --no-cache-dir -r requirements.txt; fi
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY content /content
RUN useradd --create-home appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
