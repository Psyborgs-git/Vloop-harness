"""Production execution manager backed by Rust kernel IPC (scaffold)."""

from typing import Any, Dict


class RustInfraExecutionManager:
    def dispatch_job(self, spec: Dict[str, Any], policy: Dict[str, Any]) -> str:
        raise NotImplementedError("dispatch_job not implemented (scaffold)")

    def stream_logs(self, job_id: str):
        raise NotImplementedError("stream_logs not implemented (scaffold)")

    def teardown(self, job_id: str) -> None:
        raise NotImplementedError("teardown not implemented (scaffold)")
