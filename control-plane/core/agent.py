"""Agent orchestration scaffold."""


class AgentOrchestrator:
    def run_workflow(self, objective: str, config: dict | None = None) -> dict:
        raise NotImplementedError("AgentOrchestrator not implemented (scaffold)")
