from abc import ABC, abstractmethod
from typing import Any, Dict


class IExecutionManager(ABC):
    @abstractmethod
    def dispatch_job(self, spec: Dict[str, Any], policy: Dict[str, Any]) -> str:
        raise NotImplementedError

    @abstractmethod
    def stream_logs(self, job_id: str):
        raise NotImplementedError

    @abstractmethod
    def teardown(self, job_id: str) -> None:
        raise NotImplementedError
