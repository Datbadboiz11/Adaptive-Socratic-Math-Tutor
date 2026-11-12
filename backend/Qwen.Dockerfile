# CPU pilot profile; a CUDA host can run the same app with its CUDA PyTorch.
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir torch==2.11.0 --index-url https://download.pytorch.org/whl/cpu
COPY backend/requirements-qwen.txt ./requirements-qwen.txt
RUN pip install --no-cache-dir -r requirements-qwen.txt
COPY backend/app ./app
RUN useradd --create-home appuser
USER appuser
EXPOSE 8011
CMD ["uvicorn", "app.qwen_service:app", "--host", "0.0.0.0", "--port", "8011", "--workers", "1"]
