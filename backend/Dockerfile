FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
ARG INSTALL_LOCAL_EMBEDDING=false
COPY research/retrieval/requirements.txt ./embedding-requirements.txt
RUN if [ "$INSTALL_LOCAL_EMBEDDING" = "true" ]; then pip install --no-cache-dir -r embedding-requirements.txt; fi
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/rag_migrations ./rag_migrations
COPY content /content
RUN useradd --create-home appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
