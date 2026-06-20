use std::collections::BTreeMap;
use std::sync::Arc;
use tokio::sync::Mutex;

use crate::orchestrator::executor::WorkloadExecutor;
use crate::orchestrator::state::now_unix_ms;
use crate::orchestrator::workload::{
    WorkloadClass, WorkloadLifecycleState, WorkloadRecord, WorkloadSpec,
};

#[derive(Debug, Clone)]
pub struct WorkloadStore {
    workloads: Arc<Mutex<BTreeMap<String, WorkloadRecord>>>,
    executor: Arc<WorkloadExecutor>,
}

impl WorkloadStore {
    pub fn new(executor: Arc<WorkloadExecutor>) -> Self {
        Self {
            workloads: Arc::new(Mutex::new(BTreeMap::new())),
            executor,
        }
    }

    pub async fn list(&self) -> Vec<WorkloadRecord> {
        let guard = self.workloads.lock().await;
        guard.values().cloned().collect()
    }

    pub async fn get(&self, workload_id: &str) -> Option<WorkloadRecord> {
        let guard = self.workloads.lock().await;
        guard.get(workload_id).cloned()
    }

    pub async fn create(
        &self,
        spec: WorkloadSpec,
        workflow_id: Option<String>,
    ) -> anyhow::Result<WorkloadRecord> {
        let record = self.executor.create_workload(spec, workflow_id).await?;
        let mut guard = self.workloads.lock().await;
        guard.insert(record.workload_id.clone(), record.clone());
        Ok(record)
    }

    pub async fn start(&self, workload_id: &str) -> anyhow::Result<WorkloadRecord> {
        let mut guard = self.workloads.lock().await;
        let record = guard
            .get_mut(workload_id)
            .ok_or_else(|| anyhow::anyhow!("workload {workload_id} not found"))?;

        self.executor.start_workload(record).await?;

        Ok(record.clone())
    }

    pub async fn stop(&self, workload_id: &str) -> anyhow::Result<WorkloadRecord> {
        let mut guard = self.workloads.lock().await;
        let record = guard
            .get_mut(workload_id)
            .ok_or_else(|| anyhow::anyhow!("workload {workload_id} not found"))?;

        self.executor.stop_workload(record).await?;

        Ok(record.clone())
    }

    pub async fn get_logs(&self, workload_id: &str) -> anyhow::Result<Vec<(String, String)>> {
        let guard = self.workloads.lock().await;
        let record = guard
            .get(workload_id)
            .ok_or_else(|| anyhow::anyhow!("workload {workload_id} not found"))?;

        self.executor.collect_logs(record).await
    }
}

