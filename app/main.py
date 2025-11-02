# Copyright 2024
# Directory: yt-rag/app/main.py

"""
FastAPI application for RAG (Retrieval-Augmented Generation) backend.
Provides endpoints for document seeding and question answering with citations.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, JSONResponse

from .core.config import get_settings
from .core.database import db
from .models.requests import SeedRequest, AnswerRequest
from .models.responses import SeedResponse, AnswerResponse, HealthResponse, ErrorResponse
from .services.rag import rag_service
from .data.default_documents import DEFAULT_DOCUMENTS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting RAG API application")
    
    try:
        # Initialize database connection
        await db.connect()
        
        # Check database schema
        await db.initialize_schema()
        
        logger.info("Application startup completed successfully")
        
    except Exception as e:
        logger.error(f"Application startup failed: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down RAG API application")
    await db.disconnect()


# Create FastAPI application
app = FastAPI(
    title="RAG AI Agent Backend",
    description="A minimal, production-ready FastAPI backend demonstrating Retrieval-Augmented Generation (RAG) with vector similarity search.",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # NextJS default
        "http://localhost:3001",  # Alternative port
        "https://yt-rag.vercel.app",  # Production frontend
        "*"  # Allow all for development (remove in production)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for the chat interface
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/chat", tags=["General"])
async def chat_interface():
    """Serve the chat interface."""
    return FileResponse("static/chat.html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Handle favicon requests to prevent 404 errors."""
    return Response(status_code=204)  # No Content


@app.get("/", tags=["General"])
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Welcome to RAG AI Agent Backend",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "health": "/healthz",
            "seed": "/seed",
            "answer": "/answer",
            "documents": "/documents",
            "greet": "/greet/{name}"
        }
    }


@app.get("/greet/{name}", tags=["General"])
async def greet(name: str):
    """
    Greet endpoint that returns a personalized greeting.
    
    Args:
        name (str): Name of the person to greet
        
    Returns:
        Personalized greeting message
    """
    return {"message": f"Hello, {name}! I think you are great!"}


@app.get("/healthz", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint with database connectivity test."""
    try:
        # Test database connection
        db_healthy = await db.health_check()
        
        return HealthResponse(
            status="ok" if db_healthy else "degraded",
            database_connected=db_healthy
        )
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Service unavailable: {str(e)}"
        )


@app.get("/documents", tags=["General"])
async def get_documents():
    """
    Get the default documents used for seeding the knowledge base.
    
    Returns:
        List of default documents with their chunk_id, source, and text
    """
    return {"documents": DEFAULT_DOCUMENTS}


@app.post("/seed", response_model=SeedResponse, tags=["RAG"])
async def seed_documents(request: SeedRequest = SeedRequest()):
    """
    Seed the knowledge base with documents.
    
    If no documents are provided, seeds with default policy/FAQ documents.
    Documents are chunked, embedded, and stored in the vector database.
    """
    try:
        logger.info("Starting document seeding process")
        
        # Convert request documents to the format expected by RAG service
        documents = None
        if request.docs:
            documents = [
                {
                    'chunk_id': doc.chunk_id,
                    'source': doc.source,
                    'text': doc.text
                }
                for doc in request.docs
            ]
        
        # Process documents through RAG pipeline
        inserted_count = await rag_service.seed_documents(documents)
        
        logger.info(f"Seeding completed: {inserted_count} chunks inserted")
        
        return SeedResponse(inserted=inserted_count)
        
    except Exception as e:
        logger.error(f"Seeding failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to seed documents: {str(e)}"
        )


@app.post("/answer", response_model=AnswerResponse, tags=["RAG"])
async def answer_question(request: AnswerRequest):
    """
    Answer a question using RAG (Retrieval-Augmented Generation).
    
    Pipeline:
    1. Embed the query
    2. Vector similarity search to find relevant chunks
    3. Generate answer using LLM with context
    4. Return answer with citations and debug info
    """
    try:
        logger.info(f"Processing query: '{request.query[:100]}...'")
        
        # Process query through RAG pipeline
        result = await rag_service.answer_query(
            query=request.query,
            top_k=request.top_k
        )
        
        # Convert to response model
        response = AnswerResponse(
            text=result['text'],
            citations=result['citations'],
            debug={
                'top_doc_ids': result['debug']['top_doc_ids'],
                'latency_ms': result['debug']['latency_ms']
            }
        )
        
        logger.info(f"Query processed successfully in {result['debug']['latency_ms']}ms")
        
        return response
        
    except Exception as e:
        logger.error(f"Query processing failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process query: {str(e)}"
        )


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handle 404 errors."""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "detail": "The requested endpoint does not exist",
            "available_endpoints": ["/", "/healthz", "/seed", "/answer", "/docs"]
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": "An unexpected error occurred. Please check the logs."
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
