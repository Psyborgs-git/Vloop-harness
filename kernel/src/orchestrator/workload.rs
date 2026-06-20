use anyhow::{bail, Result};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum WorkloadClass {
    Harness,
    Worker,
    Preview,
    Service,
}

impl WorkloadClass {
    pub fn as_str(&self) -> &str {
        match self {
            WorkloadClass::Harness => "harness",
            WorkloadClass::Worker => "worker",
            WorkloadClass::Preview => "preview",
            WorkloadClass::Service => "service",
        }
    }

    pub fn to_proto(&self) -> i32 {
        match self {
            WorkloadClass::Harness => 1,
            WorkloadClass::Worker => 2,
            WorkloadClass::Preview => 3,
            WorkloadClass::Service => 4,
        }
    }

    pub fn from_proto(value: i32) -> Self {
        match value {
            1 => WorkloadClass::Harness,
            2 => WorkloadClass::Worker,
            3 => WorkloadClass::Preview,
            4 => WorkloadClass::Service,
            _ => WorkloadClass::Worker,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum WorkloadLifecycleState {
    Created,
    Prepared,
    Starting,
    Running,
    Completed,
    Failed,
    Cancelling,
    Cancelled,
    GarbageCollected,
}

impl WorkloadLifecycleState {
    pub fn as_str(&self) -> &str {
        match self {
            WorkloadLifecycleState::Created => "created",
            WorkloadLifecycleState::Prepared => "prepared",
            WorkloadLifecycleState::Starting => "starting",
            WorkloadLifecycleState::Running => "running",
            WorkloadLifecycleState::Completed => "completed",
            WorkloadLifecycleState::Failed => "failed",
            WorkloadLifecycleState::Cancelling => "cancelling",
            WorkloadLifecycleState::Cancelled => "cancelled",
            WorkloadLifecycleState::GarbageCollected => "garbage_collected",
        }
    }

    pub fn to_proto(&self) -> i32 {
        match self {
            WorkloadLifecycleState::Created => 1,
            WorkloadLifecycleState::Prepared => 2,
            WorkloadLifecycleState::Starting => 3,
            WorkloadLifecycleState::Running => 4,
            WorkloadLifecycleState::Completed => 5,
            WorkloadLifecycleState::Failed => 6,
            WorkloadLifecycleState::Cancelling => 7,
            WorkloadLifecycleState::Cancelled => 8,
            WorkloadLifecycleState::GarbageCollected => 9,
        }
    }

    pub fn from_proto(value: i32) -> Self {
        match value {
            1 => WorkloadLifecycleState::Created,
            2 => WorkloadLifecycleState::Prepared,
            3 => WorkloadLifecycleState::Starting,
            4 => WorkloadLifecycleState::Running,
            5 => WorkloadLifecycleState::Completed,
            6 => WorkloadLifecycleState::Failed,
            7 => WorkloadLifecycleState::Cancelling,
            8 => WorkloadLifecycleState::Cancelled,
            9 => WorkloadLifecycleState::GarbageCollected,
            _ => WorkloadLifecycleState::Created,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkloadSpec {
    pub image: String,
    pub command: Vec<String>,
    pub env_refs: Vec<String>,
    pub workspace_id: Option<String>,
    pub requested_ports: Vec<u16>,
    pub environment: Option<std::collections::BTreeMap<String, String>>,
    pub class: Option<WorkloadClass>,
}

impl WorkloadSpec {
    pub fn merge_environment(&self) -> std::collections::HashMap<String, String> {
        self.environment
            .as_ref()
            .map(|m| m.iter().map(|(k, v)| (k.clone(), v.clone())).collect())
            .unwrap_or_default()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkloadRecord {
    pub workload_id: String,
    pub class: WorkloadClass,
    pub state: WorkloadLifecycleState,
    pub spec: WorkloadSpec,
    pub created_at_unix_ms: i64,
    pub updated_at_unix_ms: i64,
    pub exit_code: Option<i32>,
    pub termination_reason: Option<String>,
    pub exposed_ports: Vec<u16>,
    pub preview_url: Option<String>,
    pub container_id: Option<String>,
}

impl WorkloadRecord {
    pub fn transition(
        &mut self,
        next_state: WorkloadLifecycleState,
        now_unix_ms: i64,
    ) -> Result<()> {
        use WorkloadLifecycleState as S;

        let allowed = matches!(
            (&self.state, &next_state),
            (S::Created, S::Prepared)
                | (S::Prepared, S::Starting)
                | (S::Starting, S::Running)
                | (S::Running, S::Completed)
                | (S::Running, S::Failed)
                | (S::Running, S::Cancelling)
                | (S::Cancelling, S::Cancelled)
                | (S::Completed, S::GarbageCollected)
                | (S::Failed, S::GarbageCollected)
                | (S::Cancelled, S::GarbageCollected)
        );

        if !allowed {
            bail!(
                "invalid workload transition from {:?} to {:?}",
                self.state,
                next_state
            );
        }

        self.state = next_state;
        self.updated_at_unix_ms = now_unix_ms;
        Ok(())
    }
}
