# Copyright 2024
# Directory: yt-rag/app/services/embedding.py

"""
AI provider abstraction for embeddings and chat completions.
Supports both OpenAI and Anthropic with configurable models.
"""

import logging
from typing import List, Dict, Any
import openai
import anthropic
from ..core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class EmbeddingService:
    """Service for generating text embeddings using OpenAI."""
    
    def __init__(self):
        """Initialize OpenAI client for embeddings."""
        self.openai_client = openai.OpenAI(api_key=settings.openai_api_key)
        self.embed_model = settings.openai_embed_model
    
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors (1536 dimensions for text-embedding-3-small)
        """
        try:
            response = self.openai_client.embeddings.create(
                model=self.embed_model,
                input=texts
            )
            
            embeddings = [item.embedding for item in response.data]
            logger.info(f"Generated embeddings for {len(texts)} texts")
            return embeddings
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise
    
    async def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a single query.
        
        Args:
            query: Query text to embed
            
        Returns:
            Embedding vector
        """
        embeddings = await self.embed_texts([query])
        return embeddings[0]


class ChatService:
    """Service for chat completions supporting multiple AI providers."""
    
    def __init__(self):
        """Initialize chat clients based on configuration."""
        self.provider = settings.ai_provider
        
        if self.provider == "openai":
            self.client = openai.OpenAI(api_key=settings.openai_api_key)
            self.model = settings.openai_chat_model
        elif self.provider == "anthropic":
            self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            self.model = settings.anthropic_chat_model
        else:
            raise ValueError(f"Unsupported AI provider: {self.provider}")
        
        logger.info(f"Initialized chat service with {self.provider} ({self.model})")
    
    async def generate_answer(self, query: str, context_blocks: List[Dict[str, Any]]) -> str:
        """
        Generate RAG answer using context blocks.
        
        Args:
            query: User's question
            context_blocks: Retrieved chunks with metadata
            
        Returns:
            Generated answer with citations
        """
        # Build context string with citations
        context_parts = []
        for block in context_blocks:
            chunk_id = block.get('chunk_id', 'unknown')
            text = block.get('text', '')
            context_parts.append(f"[{chunk_id}] {text}")
        
        context = "\n\n".join(context_parts)
        
        system_prompt = """You are a helpful AI assistant for customer support that answers questions based on provided context.

IMPORTANT RULES:
1. For questions about policies, returns, shipping, sizing, or support: Answer ONLY using the provided context and include citations
2. For general greetings or casual conversation: You can respond naturally and friendly
3. For questions outside your knowledge base: Politely redirect to relevant policies or suggest contacting support
4. Always include citations [chunk_id] when using context information
5. Be concise but comprehensive
6. Maintain a helpful, professional tone"""

        user_prompt = f"""Context:
{context}

Question: {query}

Please provide an answer based on the context above, including appropriate citations."""

        try:
            if self.provider == "openai":
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=settings.temperature,
                    max_tokens=1000
                )
                answer = response.choices[0].message.content
                
            elif self.provider == "anthropic":
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=1000,
                    temperature=settings.temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}]
                )
                answer = response.content[0].text
            
            logger.info(f"Generated answer using {self.provider}")
            return answer or "I couldn't generate an answer."
            
        except Exception as e:
            logger.error(f"Failed to generate answer: {e}")
            return f"I encountered an error while processing your question: {str(e)}"


# Global service instances
embedding_service = EmbeddingService()
chat_service = ChatService()
