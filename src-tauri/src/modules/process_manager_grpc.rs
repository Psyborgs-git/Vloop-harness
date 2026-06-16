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
    UpdateProcessRequest, GetProcessPortsRequest, GetProcessPortsResponse,
    AssignPortRequest, AssignPortResponse,
};

fn map_process_type_to_proto(t: &str) -> i32 {
    match t {
        "APP" => pb::ProcessType::App as i32,
        "TUI" => pb::ProcessType::Tui as i32,
        "SERVICE" => pb::ProcessType::Service as i32,
        "WORKER" => pb::ProcessType::Worker as i32,
        _ => pb::ProcessType::Unspecified as i32,
    }
}

fn map_proto_to_process_type(proto_val: i32) -> String {
    match pb::ProcessType::try_from(proto_val) {
        Ok(pb::ProcessType::App) => "APP".to_string(),
        Ok(pb::ProcessType::Tui) => "TUI".to_string(),
        Ok(pb::ProcessType::Service) => "SERVICE".to_string(),
        Ok(pb::ProcessType::Worker) => "WORKER".to_string(),
        _ => "SERVICE".to_string(),
    }
}

fn map_ports_to_proto(ports: &[crate::modules::process_manager::PortBinding]) -> Vec<pb::PortBinding> {
    ports
        .iter()
        .map(|p| pb::PortBinding {
            name: p.name.clone(),
            port: p.port,
            protocol: p.protocol.clone(),
        })
        .collect()
}

fn map_proto_to_ports(proto_ports: &[pb::PortBinding]) -> Vec<crate::modules::process_manager::PortBinding> {
    proto_ports
        .iter()
        .map(|p| crate::modules::process_manager::PortBinding {
            name: p.name.clone(),
            port: p.port,
            protocol: p.protocol.clone(),
        })
        .collect()
}

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
        let _ = crate::modules::process_manager::check_and_update_all_statuses();
        let conn = self.get_conn()?;
        let mut stmt = conn
            .prepare("SELECT id, name, description, command, args, env_vars, cwd, status, created_at, updated_at, environment_id, autostart, process_type, ports FROM processes")
            .map_err(|e| Status::internal(e.to_string()))?;

        let processes_iter = stmt
            .query_map([], |row| {
                let process_type_str: Option<String> = row.get(12)?;
                let process_type_val = process_type_str.unwrap_or_else(|| "SERVICE".to_string());
                let ports_str: String = row.get(13)?;
                let ports_list: Vec<crate::modules::process_manager::PortBinding> = serde_json::from_str(&ports_str).unwrap_or_default();

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
                        process_type: map_process_type_to_proto(&process_type_val),
                        ports: map_ports_to_proto(&ports_list),
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
        let _ = crate::modules::process_manager::check_and_update_all_statuses();
        let id = request.into_inner().id;
        let conn = self.get_conn()?;
        let mut stmt = conn
            .prepare("SELECT id, name, description, command, args, env_vars, cwd, status, created_at, updated_at, environment_id, autostart, process_type, ports FROM processes WHERE id = ?1")
            .map_err(|e| Status::internal(e.to_string()))?;

        let process = stmt
            .query_row([&id], |row| {
                let process_type_str: Option<String> = row.get(12)?;
                let process_type_val = process_type_str.unwrap_or_else(|| "SERVICE".to_string());
                let ports_str: String = row.get(13)?;
                let ports_list: Vec<crate::modules::process_manager::PortBinding> = serde_json::from_str(&ports_str).unwrap_or_default();

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
                        process_type: map_process_type_to_proto(&process_type_val),
                        ports: map_ports_to_proto(&ports_list),
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
        
        let process_type_str = map_proto_to_process_type(config.process_type);
        let ports_list = map_proto_to_ports(&config.ports);
        let ports_json = serde_json::to_string(&ports_list).unwrap_or_else(|_| "[]".to_string());

        let conn = self.get_conn()?;
        conn.execute(
            "INSERT INTO processes (id, name, description, command, args, env_vars, cwd, status, created_at, updated_at, environment_id, autostart, process_type, ports) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)",
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
                process_type_str,
                ports_json,
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
        
        let process_type_str = map_proto_to_process_type(config.process_type);
        let ports_list = map_proto_to_ports(&config.ports);
        let ports_json = serde_json::to_string(&ports_list).unwrap_or_else(|_| "[]".to_string());

        let conn = self.get_conn()?;
        let affected = conn.execute(
            "UPDATE processes SET name = ?1, description = ?2, command = ?3, args = ?4, env_vars = ?5, cwd = ?6, updated_at = ?7, environment_id = ?8, autostart = ?9, process_type = ?10, ports = ?11 WHERE id = ?12",
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
                process_type_str,
                ports_json,
                req.id,
            ],
        )
        .map_err(|e| Status::internal(e.to_string()))?;

        if affected == 0 {
            return Err(Status::not_found("Process not found"));
        }

        // Just fetch it to return
        let mut stmt = conn
            .prepare("SELECT id, name, description, command, args, env_vars, cwd, status, created_at, updated_at, environment_id, autostart, process_type, ports FROM processes WHERE id = ?1")
            .unwrap();

        let process = stmt
            .query_row([&req.id], |row| {
                let process_type_str: Option<String> = row.get(12)?;
                let process_type_val = process_type_str.unwrap_or_else(|| "SERVICE".to_string());
                let ports_str: String = row.get(13)?;
                let ports_list: Vec<crate::modules::process_manager::PortBinding> = serde_json::from_str(&ports_str).unwrap_or_default();

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
                        process_type: map_process_type_to_proto(&process_type_val),
                        ports: map_ports_to_proto(&ports_list),
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
        match crate::modules::process_manager::delete_process(id) {
            Ok(_) => {
                Ok(Response::new(DeleteProcessResponse {
                    success: true,
                    error_message: String::new(),
                }))
            }
            Err(e) => {
                Ok(Response::new(DeleteProcessResponse {
                    success: false,
                    error_message: e,
                }))
            }
        }
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

    async fn get_process_ports(
        &self,
        request: Request<GetProcessPortsRequest>,
    ) -> Result<Response<GetProcessPortsResponse>, Status> {
        let req = request.into_inner();
        let ports = crate::modules::process_manager::get_process_ports(req.process_id)
            .map_err(|e| Status::internal(e.to_string()))?;
        
        Ok(Response::new(GetProcessPortsResponse {
            ports: map_ports_to_proto(&ports),
        }))
    }

    async fn assign_port(
        &self,
        request: Request<AssignPortRequest>,
    ) -> Result<Response<AssignPortResponse>, Status> {
        let req = request.into_inner();
        let binding = crate::modules::process_manager::assign_port(
            req.process_id,
            req.port_name,
            req.port,
            req.protocol,
        )
        .map_err(|e| Status::internal(e.to_string()))?;
        
        Ok(Response::new(AssignPortResponse {
            port_binding: Some(pb::PortBinding {
                name: binding.name,
                port: binding.port,
                protocol: binding.protocol,
            }),
        }))
    }
}
