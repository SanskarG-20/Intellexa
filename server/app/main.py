from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.chat import router as chat_router
from app.core.config import settings
import uvicorn

app = FastAPI(
    title=settings.APP_NAME,
    description="Backend API for Intellexa Core Chatbot",
    version="1.0.0"
)

allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# Include API routes
app.include_router(chat_router)

@app.get("/")
def read_root():
    """
    Health check endpoint.
    """
    return {
        "status": "online", 
        "service": settings.APP_NAME,
        "message": "Welcome to Intellexa Core! Start chatting at /api/v1/chat"
    }

if __name__ == "__main__":
    # Start the server using uvicorn
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=settings.DEBUG
    )
