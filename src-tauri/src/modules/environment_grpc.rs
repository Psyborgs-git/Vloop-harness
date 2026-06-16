use std::path::PathBuf;
use rusqlite::Connection;
use tonic::{Request, Response, Status};

pub mod pb {
    tonic::include_proto!("environment");
}

use pb::environment_manager_service_server::EnvironmentManagerService;
use pb::{
    CreateEnvironmentRequest, DeleteEnvironmentRequest, DeleteEnvironmentResponse,
    EnvironmentConfig as GrpcEnvironmentConfig, EnvironmentDetail as GrpcEnvironmentDetail,
    EnvironmentType as GrpcEnvironmentType, GetEnvironmentRequest, ListEnvironmentsRequest,
    ListEnvironmentsResponse, UpdateEnvironmentRequest,
};

pub struct MyEnvironmentManagerService {
    db_path: PathBuf,
}

impl MyEnvironmentManagerService {
    pub fn new(db_path: PathBuf) -> Self {
        // Initialize DB
        if let Ok(conn) = Connection::open(&db_path) {
            let _ = conn.execute(
                "CREATE TABLE IF NOT EXISTS environments (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    env_type TEXT NOT NULL,
                    image TEXT,
                    host TEXT,
                    user TEXT,
                    extra_config TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )",
                (),
            );

            // Migrations: Check if columns exist, add if missing
            if let Ok(mut stmt) = conn.prepare("PRAGMA table_info(environments)") {
                let mut has_path = false;
                let mut has_python_path = false;
                if let Ok(rows) = stmt.query_map([], |row| Ok(row.get::<_, String>(1)?)) {
                    for col_name in rows.flatten() {
                        if col_name == "path" {
                            has_path = true;
                        }
                        if col_name == "python_path" {
                            has_python_path = true;
                        }
                    }
                }
                if !has_path {
                    let _ = conn.execute("ALTER TABLE environments ADD COLUMN path TEXT", []);
                }
                if !has_python_path {
                    let _ = conn.execute("ALTER TABLE environments ADD COLUMN python_path TEXT", []);
                }
            }

            // Check if we need to seed the default local environment
            let mut stmt = conn.prepare("SELECT count(*) FROM environments").unwrap();
            let count: i64 = stmt.query_row([], |row| row.get(0)).unwrap_or(0);

            if count == 0 {
                let now = chrono::Utc::now().to_rfc3339();
                let _ = conn.execute(
                    "INSERT INTO environments (id, name, description, env_type, extra_config, created_at, updated_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)",
                    rusqlite::params![
                        "default-local-env-id",
                        "Local Machine",
                        "Default local execution environment",
                        "Local",
                        "{}",
                        now,
                        now,
                    ],
                );
            }
        }

        Self { db_path }
    }

    fn get_conn(&self) -> Result<Connection, Status> {
        Connection::open(&self.db_path)
            .map_err(|e| Status::internal(format!("Failed to open DB: {}", e)))
    }
}

#[tonic::async_trait]
impl EnvironmentManagerService for MyEnvironmentManagerService {
    async fn list_environments(
        &self,
        _request: Request<ListEnvironmentsRequest>,
    ) -> Result<Response<ListEnvironmentsResponse>, Status> {
        let conn = self.get_conn()?;
        let mut stmt = conn
            .prepare("SELECT id, name, description, env_type, image, host, user, extra_config, created_at, updated_at, path, python_path FROM environments")
            .map_err(|e| Status::internal(e.to_string()))?;

        let envs_iter = stmt
            .query_map([], |row| {
                let id: String = row.get(0)?;
                let type_str: String = row.get(3)?;
                let env_type = match type_str.as_str() {
                    "Docker" => GrpcEnvironmentType::Docker as i32,
                    "Ssh" => GrpcEnvironmentType::Ssh as i32,
                    "Python" => GrpcEnvironmentType::Python as i32,
                    _ => GrpcEnvironmentType::Local as i32,
                };

                // Check if SSH key exists in vault
                let has_key = crate::modules::vault::get_key(&format!("ssh_key_{}", id)).is_some();
                let ssh_key = if has_key { "********".to_string() } else { String::new() };

                Ok(GrpcEnvironmentDetail {
                    id,
                    name: row.get(1)?,
                    description: row.get(2)?,
                    config: Some(GrpcEnvironmentConfig {
                        r#type: env_type,
                        image: row.get::<_, Option<String>>(4)?.unwrap_or_default(),
                        host: row.get::<_, Option<String>>(5)?.unwrap_or_default(),
                        user: row.get::<_, Option<String>>(6)?.unwrap_or_default(),
                        extra_config: row.get(7)?,
                        path: row.get::<_, Option<String>>(10)?.unwrap_or_default(),
                        python_path: row.get::<_, Option<String>>(11)?.unwrap_or_default(),
                        ssh_key,
                    }),
                    created_at: row.get(8)?,
                    updated_at: row.get(9)?,
                })
            })
            .map_err(|e| Status::internal(e.to_string()))?;

        let mut environments = Vec::new();
        for e in envs_iter {
            if let Ok(env) = e {
                environments.push(env);
            }
        }

        Ok(Response::new(ListEnvironmentsResponse { environments }))
    }

    async fn get_environment(
        &self,
        request: Request<GetEnvironmentRequest>,
    ) -> Result<Response<GrpcEnvironmentDetail>, Status> {
        let id = request.into_inner().id;
        let conn = self.get_conn()?;
        let mut stmt = conn
            .prepare("SELECT id, name, description, env_type, image, host, user, extra_config, created_at, updated_at, path, python_path FROM environments WHERE id = ?1")
            .map_err(|e| Status::internal(e.to_string()))?;

        let id_clone = id.clone();
        let env = stmt
            .query_row([&id], |row| {
                let type_str: String = row.get(3)?;
                let env_type = match type_str.as_str() {
                    "Docker" => GrpcEnvironmentType::Docker as i32,
                    "Ssh" => GrpcEnvironmentType::Ssh as i32,
                    "Python" => GrpcEnvironmentType::Python as i32,
                    _ => GrpcEnvironmentType::Local as i32,
                };

                // Check if SSH key exists in vault
                let has_key = crate::modules::vault::get_key(&format!("ssh_key_{}", id_clone)).is_some();
                let ssh_key = if has_key { "********".to_string() } else { String::new() };

                Ok(GrpcEnvironmentDetail {
                    id: id_clone,
                    name: row.get(1)?,
                    description: row.get(2)?,
                    config: Some(GrpcEnvironmentConfig {
                        r#type: env_type,
                        image: row.get::<_, Option<String>>(4)?.unwrap_or_default(),
                        host: row.get::<_, Option<String>>(5)?.unwrap_or_default(),
                        user: row.get::<_, Option<String>>(6)?.unwrap_or_default(),
                        extra_config: row.get(7)?,
                        path: row.get::<_, Option<String>>(10)?.unwrap_or_default(),
                        python_path: row.get::<_, Option<String>>(11)?.unwrap_or_default(),
                        ssh_key,
                    }),
                    created_at: row.get(8)?,
                    updated_at: row.get(9)?,
                })
            })
            .map_err(|_| Status::not_found("Environment not found"))?;

        Ok(Response::new(env))
    }

    async fn create_environment(
        &self,
        request: Request<CreateEnvironmentRequest>,
    ) -> Result<Response<GrpcEnvironmentDetail>, Status> {
        let req = request.into_inner();
        let id = uuid::Uuid::new_v4().to_string();
        let now = chrono::Utc::now().to_rfc3339();
        
        let mut config = req.config.unwrap_or_default();
        let env_type_str = match GrpcEnvironmentType::try_from(config.r#type) {
            Ok(GrpcEnvironmentType::Docker) => "Docker",
            Ok(GrpcEnvironmentType::Ssh) => "Ssh",
            Ok(GrpcEnvironmentType::Python) => "Python",
            _ => "Local",
        };

        // Save SSH key to vault if provided
        if env_type_str == "Ssh" && !config.ssh_key.is_empty() && config.ssh_key != "********" {
            crate::modules::vault::set_key(&format!("ssh_key_{}", id), &config.ssh_key);
        }

        let conn = self.get_conn()?;
        conn.execute(
            "INSERT INTO environments (id, name, description, env_type, image, host, user, extra_config, created_at, updated_at, path, python_path) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)",
            rusqlite::params![
                id,
                req.name,
                req.description,
                env_type_str,
                if config.image.is_empty() { None } else { Some(&config.image) },
                if config.host.is_empty() { None } else { Some(&config.host) },
                if config.user.is_empty() { None } else { Some(&config.user) },
                config.extra_config,
                now,
                now,
                if config.path.is_empty() { None } else { Some(&config.path) },
                if config.python_path.is_empty() { None } else { Some(&config.python_path) },
            ],
        )
        .map_err(|e| Status::internal(e.to_string()))?;

        // Mask returning key
        if !config.ssh_key.is_empty() {
            config.ssh_key = "********".to_string();
        }

        let detail = GrpcEnvironmentDetail {
            id,
            name: req.name,
            description: req.description,
            config: Some(config),
            created_at: now.clone(),
            updated_at: now,
        };

        Ok(Response::new(detail))
    }

    async fn update_environment(
        &self,
        request: Request<UpdateEnvironmentRequest>,
    ) -> Result<Response<GrpcEnvironmentDetail>, Status> {
        let req = request.into_inner();
        let now = chrono::Utc::now().to_rfc3339();
        
        let config = req.config.unwrap_or_default();
        let env_type_str = match GrpcEnvironmentType::try_from(config.r#type) {
            Ok(GrpcEnvironmentType::Docker) => "Docker",
            Ok(GrpcEnvironmentType::Ssh) => "Ssh",
            Ok(GrpcEnvironmentType::Python) => "Python",
            _ => "Local",
        };

        // Save SSH key to vault if provided
        if env_type_str == "Ssh" && !config.ssh_key.is_empty() && config.ssh_key != "********" {
            crate::modules::vault::set_key(&format!("ssh_key_{}", req.id), &config.ssh_key);
        }

        let conn = self.get_conn()?;
        let affected = conn.execute(
            "UPDATE environments SET name = ?1, description = ?2, env_type = ?3, image = ?4, host = ?5, user = ?6, extra_config = ?7, updated_at = ?8, path = ?9, python_path = ?10 WHERE id = ?11",
            rusqlite::params![
                req.name,
                req.description,
                env_type_str,
                if config.image.is_empty() { None } else { Some(&config.image) },
                if config.host.is_empty() { None } else { Some(&config.host) },
                if config.user.is_empty() { None } else { Some(&config.user) },
                config.extra_config,
                now,
                if config.path.is_empty() { None } else { Some(&config.path) },
                if config.python_path.is_empty() { None } else { Some(&config.python_path) },
                req.id,
            ],
        )
        .map_err(|e| Status::internal(e.to_string()))?;

        if affected == 0 {
            return Err(Status::not_found("Environment not found"));
        }

        let mut stmt = conn
            .prepare("SELECT id, name, description, env_type, image, host, user, extra_config, created_at, updated_at, path, python_path FROM environments WHERE id = ?1")
            .unwrap();

        let env = stmt
            .query_row([&req.id], |row| {
                let type_str: String = row.get(3)?;
                let env_type = match type_str.as_str() {
                    "Docker" => GrpcEnvironmentType::Docker as i32,
                    "Ssh" => GrpcEnvironmentType::Ssh as i32,
                    "Python" => GrpcEnvironmentType::Python as i32,
                    _ => GrpcEnvironmentType::Local as i32,
                };

                let has_key = crate::modules::vault::get_key(&format!("ssh_key_{}", req.id)).is_some();
                let ssh_key = if has_key { "********".to_string() } else { String::new() };

                Ok(GrpcEnvironmentDetail {
                    id: row.get(0)?,
                    name: row.get(1)?,
                    description: row.get(2)?,
                    config: Some(GrpcEnvironmentConfig {
                        r#type: env_type,
                        image: row.get::<_, Option<String>>(4)?.unwrap_or_default(),
                        host: row.get::<_, Option<String>>(5)?.unwrap_or_default(),
                        user: row.get::<_, Option<String>>(6)?.unwrap_or_default(),
                        extra_config: row.get(7)?,
                        path: row.get::<_, Option<String>>(10)?.unwrap_or_default(),
                        python_path: row.get::<_, Option<String>>(11)?.unwrap_or_default(),
                        ssh_key,
                    }),
                    created_at: row.get(8)?,
                    updated_at: row.get(9)?,
                })
            })
            .map_err(|_| Status::internal("Failed to retrieve after update"))?;

        Ok(Response::new(env))
    }

    async fn delete_environment(
        &self,
        request: Request<DeleteEnvironmentRequest>,
    ) -> Result<Response<DeleteEnvironmentResponse>, Status> {
        let id = request.into_inner().id;
        if id == "default-local-env-id" {
            return Err(Status::invalid_argument("Cannot delete the default local environment"));
        }

        let conn = self.get_conn()?;
        let affected = conn
            .execute("DELETE FROM environments WHERE id = ?1", [&id])
            .map_err(|e| Status::internal(e.to_string()))?;

        // Also clean up vault keys
        crate::modules::vault::delete_key(&format!("ssh_key_{}", id));

        Ok(Response::new(DeleteEnvironmentResponse {
            success: affected > 0,
            error_message: if affected > 0 { String::new() } else { "Environment not found".to_string() },
        }))
    }
}
