from fastapi import FastAPI
from app.api.v1.chat import router as chat_router
from app.core.config import settings
import uvicorn

app = FastAPI(
    title=settings.APP_NAME,
    description="Backend API for Intellexa Core Chatbot",
    version="1.0.0"
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
