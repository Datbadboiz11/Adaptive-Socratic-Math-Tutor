"""Health and durable internal-demo sessions. No paid API calls."""
import os
import logging
from uuid import uuid4

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.sessions import router, ApiError, tutor_enabled

app = FastAPI(title="Mở — Socratic tutor API", version="0.3.0")
app.include_router(router)
logging.getLogger('mo.sessions').setLevel(logging.INFO)


@app.middleware('http')
async def trace(request: Request, call_next):
    request.state.trace_id = str(uuid4())
    response = await call_next(request)
    response.headers['X-Trace-ID'] = request.state.trace_id
    response.headers['Cache-Control'] = 'no-store'
    return response


def error_response(request, status, code, message, retryable=False):
    return JSONResponse(status_code=status, content={
        'code': code, 'message': message, 'retryable': retryable,
        'trace_id': getattr(request.state, 'trace_id', None),
    })


@app.exception_handler(ApiError)
async def api_error(request, error):
    return error_response(request, error.status, error.code, error.message, error.retryable)


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    return error_response(request, 422, 'invalid_input', 'Dữ liệu không đúng cấu trúc hoặc vượt giới hạn. Kiểm tra nội dung và phiên bản phiên.')


@app.exception_handler(psycopg.Error)
async def database_error(request, error):
    logging.getLogger('mo.sessions').error('database failure trace=%s sqlstate=%s', getattr(request.state, 'trace_id', None), error.sqlstate)
    return error_response(request, 503, 'database_unavailable', 'Chưa thể lưu/đọc dữ liệu. Giữ bài làm và thử lại cùng request.', True)


@app.get("/health/live")
def live():
    return {"status": "ok", "phase": "socratic_tutor", "tutoring_enabled": tutor_enabled()}


@app.get('/health')
@app.get("/health/ready")
def ready():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn and not os.environ.get("PGHOST"):
        return JSONResponse(status_code=503, content={"status": "not_ready", "database": "unconfigured"})
    try:
        with psycopg.connect(dsn or "", connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass('schema_migrations'), to_regclass('sessions'), to_regclass('turn_jobs')")
                if not all(cursor.fetchone()):
                    return JSONResponse(status_code=503, content={"status": "not_ready", "database": "schema_missing"})
    except psycopg.Error:
        # Connection details can include passwords; never expose the exception.
        return JSONResponse(status_code=503, content={"status": "not_ready", "database": "unavailable"})
    return {"status": "ready", "database": "connected", "tutoring_enabled": tutor_enabled()}
