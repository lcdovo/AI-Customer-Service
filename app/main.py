from contextlib import asynccontextmanager
import logging
import os
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.config.config import settings
from app.utils.database import init_database, close_redis
from app.services.llm_service import LLMService
from app.utils.tracking import get_tracer, structured_logger, generate_trace_id
from app.routers.users import router as users_router
from app.routers.sessions import router as sessions_router
from app.routers.tickets import router as tickets_router
from app.routers.chat import router as chat_router
from app.routers.analytics import router as analytics_router
from app.routers.feedback import router as feedback_router

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

llm_service = LLMService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    try:
        await init_database()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.warning(f"Database initialization failed (will auto-create on first use): {e}")

    yield

    logger.info("Shutting down...")
    await llm_service.close()
    await close_redis()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="企业级智能客服与工单自动处理系统",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def tracing_middleware(request: Request, call_next):
    """全链路追踪中间件"""
    trace_id = request.headers.get("X-Trace-Id", generate_trace_id())
    request.state.trace_id = trace_id
    request.state.start_time = time.time()

    try:
        response = await call_next(request)
        duration_ms = int((time.time() - request.state.start_time) * 1000)

        response.headers["X-Trace-Id"] = trace_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        structured_logger.log_response(
            trace_id=trace_id,
            status_code=response.status_code,
            duration_ms=duration_ms,
            method=request.method,
            path=request.url.path,
        )

        tracer = get_tracer()
        if response.status_code < 400:
            tracer._metrics.record_response(duration_ms, True)
        else:
            tracer._metrics.record_response(duration_ms, False)
            tracer._metrics.record_error("http_error", f"Status: {response.status_code}")

        return response
    except Exception as exc:
        duration_ms = int((time.time() - request.state.start_time) * 1000)
        structured_logger.log_error(
            trace_id=trace_id,
            error_type="internal_error",
            error_message=str(exc),
            method=request.method,
            path=request.url.path,
            duration_ms=duration_ms,
        )
        raise


app.include_router(users_router)
app.include_router(sessions_router)
app.include_router(tickets_router)
app.include_router(chat_router)
app.include_router(analytics_router)
app.include_router(feedback_router)

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", response_model=dict)
async def health_check():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": "Internal Server Error",
            "detail": str(exc) if settings.DEBUG else "An unexpected error occurred",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=1,
    )
