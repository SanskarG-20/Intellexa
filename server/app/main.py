from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api.v1.chat import router as chat_router
from app.api.v1.memory import router as memory_router
from app.api.v1.code import router as code_router
from app.api.v1.project_context import router as project_context_router
from app.api.v1.dependency_graph import router as dependency_graph_router
from app.routes.code_workspace_routes import router as code_workspace_router
from app.realtime import socket_app
from app.core.config import settings
from app.services.memory.embedding_service import validate_embedding_service
import uvicorn
import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting Intellexa Core...")
    
    # Validate embedding service
    if settings.EMBEDDING_VALIDATE_ON_STARTUP:
        try:
            await validate_embedding_service()
        except Exception as e:
            logger.warning(f"Embedding service validation failed: {e}")
    else:
        logger.info("Embedding startup validation skipped by configuration.")
    
    logger.info("Intellexa Core ready!")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Intellexa Core...")


app = FastAPI(
    title=settings.APP_NAME,
    description="Backend API for Intellexa Core Chatbot",
    version="1.0.0",
    lifespan=lifespan
)

allowed_origins = settings.get_cors_origins()
allow_all_origins = "*" in allowed_origins
if allow_all_origins:
    allowed_origins = ["*"]

allow_origin_regex = (
    None
    if allow_all_origins
    else (settings.CORS_ALLOW_ORIGIN_REGEX.strip() or r"https?://(localhost|127\.0\.0\.1)(:\d+)?$")
)
allow_credentials = False if allow_all_origins else True

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(chat_router)
app.include_router(memory_router)
app.include_router(code_router)
app.include_router(project_context_router)
app.include_router(dependency_graph_router)
app.include_router(code_workspace_router)

# Realtime collaboration runtime (Socket.IO) at /realtime/socket.io
app.mount("/realtime", socket_app)

@app.get("/")
def read_root():
    """
    Health check endpoint.
    """
    return {
        "status": "online", 
        "service": settings.APP_NAME,
        "message": "Welcome to Intellexa Core! Start chatting at /api/v1/chat",
        "realtime": {
            "socket_path": settings.COLLAB_SOCKET_PATH,
            "collaboration_enabled": settings.COLLABORATION_ENABLED,
        },
    }

if __name__ == "__main__":
    # Start the server using uvicorn
    uvicorn.run(
        "app.main:app", 
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
