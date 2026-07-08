import os
import structlog
from typing import List, Tuple
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from config import settings

logger = structlog.get_logger(__name__)

class LongTermMemory:
    """
    Long-term memory store using FAISS and local embeddings.
    This allows the agent to recall information from past tasks.
    """
    
    def __init__(self):
        self.index_path = settings.faiss_index_path
        self.embeddings = FastEmbedEmbeddings(model_name=settings.embedding_model)
        self.vector_store = self._load_or_create_store()

    def _load_or_create_store(self) -> FAISS:
        """Loads the FAISS index from disk or creates a new one if it doesn't exist."""
        if os.path.exists(os.path.join(self.index_path, "index.faiss")):
            try:
                logger.info("Loading existing FAISS index", path=self.index_path)
                return FAISS.load_local(
                    self.index_path, 
                    self.embeddings, 
                    allow_dangerous_deserialization=True
                )
            except Exception as e:
                logger.error("Failed to load FAISS index, creating new one", error=str(e))
        
        logger.info("Creating new FAISS index")
        # Create a dummy entry to initialize the index
        return FAISS.from_texts(
            ["Initial memory state"], 
            self.embeddings, 
            metadatas=[{"source": "system", "task_id": "init"}]
        )

    def retrieve(self, query: str, top_k: int = 3) -> List[Tuple[str, float]]:
        """
        Retrieves relevant memories for a given query.
        Returns a list of (text, score) tuples.
        """
        try:
            results = self.vector_store.similarity_search_with_score(query, k=top_k)
            # FAISS scores are L2 distance (lower is better), we normalize roughly
            return [(doc.page_content, doc.metadata.get("score", 1.0)) for doc, score in results]
        except Exception as e:
            logger.error("Memory retrieval failed", error=str(e))
            return []

    def write(self, text: str, task_id: str, summary: str):
        """
        Adds a new memory to the store and persists it.
        """
        try:
            self.vector_store.add_texts(
                [text], 
                metadatas=[{"task_id": task_id, "summary": summary}]
            )
            # Save to disk
            os.makedirs(self.index_path, exist_ok=True)
            self.vector_store.save_local(self.index_path)
            logger.info("Memory persisted", task_id=task_id)
        except Exception as e:
            logger.error("Failed to write to memory", error=str(e))
