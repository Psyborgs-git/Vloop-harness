use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use rusqlite::Connection;
use tonic::{Request, Response, Status};

pub mod pb {
    tonic::include_proto!("process");
}

use pb::process_manager_service_server::ProcessManagerService;
use pb::{
    CreateProcessRequest, DeleteProcessRequest, DeleteProcessResponse, GetProcessRequest,
    ListProcessesRequest, ListProcessesResponse, ProcessConfig, ProcessDetail,
    ProcessStatusResponse, PullProcessRequest, StartProcessRequest, StopProcessRequest,
    UpdateProcessRequest,
};

pub struct MyProcessManagerService {
    db_path: PathBuf,
    // Add memory map for active process statuses
    _active_processes: Arc<Mutex<std::collections::HashMap<String, String>>>,
}

impl MyProcessManagerService {
    pub fn new(db_path: PathBuf) -> Self {
        Self {
            db_path,
            _active_processes: Arc::new(Mutex::new(std::collections::HashMap::new())),
        }
    }

    fn get_conn(&self) -> Result<Connection, Status> {
        Connection::open(&self.db_path)
            .map_err(|e| Status::internal(format!("Failed to open DB: {}", e)))
    }
}

#[tonic::async_trait]
impl ProcessManagerService for MyProcessManagerService {
    async fn list_processes(
        &self,
        _request: Request<ListProcessesRequest>,
    ) -> Result<Response<ListProcessesResponse>, Status> {
        let conn = self.get_conn()?;
        let mut stmt = conn
            .prepare("SELECT id, name, description, command, args, env_vars, cwd, status, created_at, updated_at, environment_id, autostart FROM processes")
            .map_err(|e| Status::internal(e.to_string()))?;

        let processes_iter = stmt
            .query_map([], |row| {
                Ok(ProcessDetail {
                    id: row.get(0)?,
                    name: row.get(1)?,
                    description: row.get(2)?,
                    config: Some(ProcessConfig {
                        command: row.get(3)?,
                        args: serde_json::from_str(&row.get::<_, String>(4)?).unwrap_or_default(),
                        env_vars: row.get(5)?,
                        cwd: row.get(6)?,
                        environment_id: row.get(10)?,
                        autostart: row.get::<_, bool>(11).unwrap_or(false),
                    }),
                    status: row.get(7)?,
                    created_at: row.get(8)?,
                    updated_at: row.get(9)?,
                })
            })
            .map_err(|e| Status::internal(e.to_string()))?;

        let mut processes = Vec::new();
        for p in processes_iter {
            if let Ok(process) = p {
                processes.push(process);
            }
        }

        Ok(Response::new(ListProcessesResponse { processes }))
    }

    async fn get_process(
        &self,
        request: Request<GetProcessRequest>,
    ) -> Result<Response<ProcessDetail>, Status> {
        let id = request.into_inner().id;
        let conn = self.get_conn()?;
        let mut stmt = conn
            .prepare("SELECT id, name, description, command, args, env_vars, cwd, status, created_at, updated_at, environment_id, autostart FROM processes WHERE id = ?1")
            .map_err(|e| Status::internal(e.to_string()))?;

        let process = stmt
            .query_row([&id], |row| {
                Ok(ProcessDetail {
                    id: row.get(0)?,
                    name: row.get(1)?,
                    description: row.get(2)?,
                    config: Some(ProcessConfig {
                        command: row.get(3)?,
                        args: serde_json::from_str(&row.get::<_, String>(4)?).unwrap_or_default(),
                        env_vars: row.get(5)?,
                        cwd: row.get(6)?,
                        environment_id: row.get(10)?,
                        autostart: row.get::<_, bool>(11).unwrap_or(false),
                    }),
                    status: row.get(7)?,
                    created_at: row.get(8)?,
                    updated_at: row.get(9)?,
                })
            })
            .map_err(|_| Status::not_found("Process not found"))?;

        Ok(Response::new(process))
    }

    async fn create_process(
        &self,
        request: Request<CreateProcessRequest>,
    ) -> Result<Response<ProcessDetail>, Status> {
        let req = request.into_inner();
        let id = uuid::Uuid::new_v4().to_string();
        let now = chrono::Utc::now().to_rfc3339();
        
        let config = req.config.unwrap_or_default();
        let args_json = serde_json::to_string(&config.args).unwrap_or_else(|_| "[]".to_string());

        let conn = self.get_conn()?;
        conn.execute(
            "INSERT INTO processes (id, name, description, command, args, env_vars, cwd, status, created_at, updated_at, environment_id, autostart) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)",
            rusqlite::params![
                id,
                req.name,
                req.description,
                config.command,
                args_json,
                config.env_vars,
                config.cwd,
                "stopped",
                now,
                now,
                config.environment_id,
                config.autostart,
            ],
        )
        .map_err(|e| Status::internal(e.to_string()))?;

        // Return the created process
        let detail = ProcessDetail {
            id,
            name: req.name,
            description: req.description,
            config: Some(config),
            status: "stopped".to_string(),
            created_at: now.clone(),
            updated_at: now,
        };

        Ok(Response::new(detail))
    }

    async fn update_process(
        &self,
        request: Request<UpdateProcessRequest>,
    ) -> Result<Response<ProcessDetail>, Status> {
        let req = request.into_inner();
        let now = chrono::Utc::now().to_rfc3339();
        
        let config = req.config.unwrap_or_default();
        let args_json = serde_json::to_string(&config.args).unwrap_or_else(|_| "[]".to_string());

        let conn = self.get_conn()?;
        let affected = conn.execute(
            "UPDATE processes SET name = ?1, description = ?2, command = ?3, args = ?4, env_vars = ?5, cwd = ?6, updated_at = ?7, environment_id = ?8, autostart = ?9 WHERE id = ?10",
            rusqlite::params![
                req.name,
                req.description,
                config.command,
                args_json,
                config.env_vars,
                config.cwd,
                now,
                config.environment_id,
                config.autostart,
                req.id,
            ],
        )
        .map_err(|e| Status::internal(e.to_string()))?;

        if affected == 0 {
            return Err(Status::not_found("Process not found"));
        }

        // Just fetch it to return
        let mut stmt = conn
            .prepare("SELECT id, name, description, command, args, env_vars, cwd, status, created_at, updated_at, environment_id, autostart FROM processes WHERE id = ?1")
            .unwrap();

        let process = stmt
            .query_row([&req.id], |row| {
                Ok(ProcessDetail {
                    id: row.get(0)?,
                    name: row.get(1)?,
                    description: row.get(2)?,
                    config: Some(ProcessConfig {
                        command: row.get(3)?,
                        args: serde_json::from_str(&row.get::<_, String>(4)?).unwrap_or_default(),
                        env_vars: row.get(5)?,
                        cwd: row.get(6)?,
                        environment_id: row.get(10)?,
                        autostart: row.get::<_, bool>(11).unwrap_or(false),
                    }),
                    status: row.get(7)?,
                    created_at: row.get(8)?,
                    updated_at: row.get(9)?,
                })
            })
            .map_err(|_| Status::internal("Failed to retrieve after update"))?;

        Ok(Response::new(process))
    }

    async fn delete_process(
        &self,
        request: Request<DeleteProcessRequest>,
    ) -> Result<Response<DeleteProcessResponse>, Status> {
        let id = request.into_inner().id;
        let conn = self.get_conn()?;
        let affected = conn
            .execute("DELETE FROM processes WHERE id = ?1", [&id])
            .map_err(|e| Status::internal(e.to_string()))?;

        Ok(Response::new(DeleteProcessResponse {
            success: affected > 0,
            error_message: if affected > 0 { String::new() } else { "Process not found".to_string() },
        }))
    }

    async fn start_process(
        &self,
        request: Request<StartProcessRequest>,
    ) -> Result<Response<ProcessStatusResponse>, Status> {
        let id = request.into_inner().id;
        match crate::modules::process_manager::start_process(id.clone()) {
            Ok(_) => {
                Ok(Response::new(ProcessStatusResponse {
                    success: true,
                    status: "running".to_string(),
                    error_message: String::new(),
                }))
            }
            Err(e) => {
                Ok(Response::new(ProcessStatusResponse {
                    success: false,
                    status: "error".to_string(),
                    error_message: e,
                }))
            }
        }
    }

    async fn stop_process(
        &self,
        request: Request<StopProcessRequest>,
    ) -> Result<Response<ProcessStatusResponse>, Status> {
        let id = request.into_inner().id;
        match crate::modules::process_manager::stop_process(id.clone()) {
            Ok(_) => {
                Ok(Response::new(ProcessStatusResponse {
                    success: true,
                    status: "stopped".to_string(),
                    error_message: String::new(),
                }))
            }
            Err(e) => {
                Ok(Response::new(ProcessStatusResponse {
                    success: false,
                    status: "error".to_string(),
                    error_message: e,
                }))
            }
        }
    }

    async fn pull_process(
        &self,
        _request: Request<PullProcessRequest>,
    ) -> Result<Response<ProcessDetail>, Status> {
        // Mock pulling
        Err(Status::unimplemented("Pulling processes is not yet implemented"))
    }
}
