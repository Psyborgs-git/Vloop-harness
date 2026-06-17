from abc import ABC, abstractmethod
from typing import List, Dict, Any

class IVectorStore(ABC):
    """
    Interface for vector-based memory storage.
    Used for storing and retrieving agent embeddings/memories.
    """
    
    @abstractmethod
    def add_document(self, collection_name: str, document_id: str, text: str, metadata: Dict[str, Any] = None) -> None:
        pass

    @abstractmethod
    def search(self, collection_name: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        pass

class IRelationalDB(ABC):
    """
    Interface for structured relational data storage.
    Used for audit logs, task states, and metrics.
    """
    
    @abstractmethod
    def connect(self) -> None:
        pass

    @abstractmethod
    def execute_query(self, query: str, params: tuple = ()) -> List[tuple]:
        pass
    
    @abstractmethod
    def close(self) -> None:
        pass

class IExecutionManager(ABC):
    """
    Interface for dispatching and managing sandboxed code execution.
    Abstracts local Docker and remote Kubernetes.
    """
    
    @abstractmethod
    def dispatch_job(self, spec: Dict[str, Any], policy: Dict[str, Any]) -> str:
        """
        Dispatches a job. Returns a unique Job ID.
        spec: Code to run, image to use, entrypoint.
        policy: DSPy-generated security policy (network access, limits).
        """
        pass

    @abstractmethod
    def stream_logs(self, job_id: str) -> Any:
        """
        Returns an iterator/generator of log lines (stdout/stderr) for the given job.
        """
        pass

    @abstractmethod
    def teardown(self, job_id: str) -> None:
        """
        Aggressively terminates and deletes the job/container.
        """
        pass
