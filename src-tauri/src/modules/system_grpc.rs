use std::collections::HashMap;
use tonic::{Request, Response, Status};

pub mod pb {
    tonic::include_proto!("system");
}

use pb::system_service_server::SystemService;
use pb::{
    GetHealthRequest, HealthReport, GetConfigRequest, ConfigResponse,
    UpdateConfigRequest, RestartServicesRequest, RestartServicesResponse,
};

#[derive(Default)]
pub struct MySystemService {}

#[tonic::async_trait]
impl SystemService for MySystemService {
    async fn get_health(&self, _request: Request<GetHealthRequest>) -> Result<Response<HealthReport>, Status> {
        let repo_root = crate::modules::main::get_repo_root();
        let data_dir = crate::modules::main::get_data_dir(&repo_root);
        let health = crate::modules::health::check_system_health(&repo_root, &data_dir);
        
        Ok(Response::new(HealthReport {
            python_ok: health.python_ok,
            node_ok: health.node_ok,
            db_accessible: health.db_accessible,
            details: health.details,
        }))
    }

    async fn get_config(&self, _request: Request<GetConfigRequest>) -> Result<Response<ConfigResponse>, Status> {
        let repo_root = crate::modules::main::get_repo_root();
        let vars = crate::modules::settings_protocol::read_env_vars(&repo_root);
        
        Ok(Response::new(ConfigResponse {
            dspy_lm_provider: vars.get("DSPY_LM_PROVIDER").cloned().unwrap_or_default(),
            dspy_lm_model: vars.get("DSPY_LM_MODEL").cloned().unwrap_or_default(),
            anthropic_api_key: vars.get("ANTHROPIC_API_KEY").cloned().unwrap_or_default(),
            openai_api_key: vars.get("OPENAI_API_KEY").cloned().unwrap_or_default(),
            ollama_base_url: vars.get("OLLAMA_BASE_URL").cloned().unwrap_or_default(),
            harness_port: vars.get("HARNESS_PORT").cloned().unwrap_or_default(),
            vite_port: vars.get("VITE_PORT").cloned().unwrap_or_default(),
            state_db_path: vars.get("STATE_DB_PATH").cloned().unwrap_or_default(),
            log_dir: vars.get("LOG_DIR").cloned().unwrap_or_default(),
        }))
    }

    async fn update_config(&self, request: Request<UpdateConfigRequest>) -> Result<Response<ConfigResponse>, Status> {
        let req = request.into_inner();
        let mut updates = HashMap::new();
        updates.insert("DSPY_LM_PROVIDER".to_string(), req.dspy_lm_provider.clone());
        updates.insert("DSPY_LM_MODEL".to_string(), req.dspy_lm_model.clone());
        updates.insert("ANTHROPIC_API_KEY".to_string(), req.anthropic_api_key.clone());
        updates.insert("OPENAI_API_KEY".to_string(), req.openai_api_key.clone());
        updates.insert("OLLAMA_BASE_URL".to_string(), req.ollama_base_url.clone());
        updates.insert("HARNESS_PORT".to_string(), req.harness_port.clone());
        updates.insert("VITE_PORT".to_string(), req.vite_port.clone());
        updates.insert("STATE_DB_PATH".to_string(), req.state_db_path.clone());
        updates.insert("LOG_DIR".to_string(), req.log_dir.clone());

        let repo_root = crate::modules::main::get_repo_root();
        if let Err(e) = crate::modules::settings_protocol::update_env_file(&repo_root, &updates) {
            return Err(Status::internal(format!("Failed to update env file: {}", e)));
        }

        Ok(Response::new(ConfigResponse {
            dspy_lm_provider: req.dspy_lm_provider,
            dspy_lm_model: req.dspy_lm_model,
            anthropic_api_key: req.anthropic_api_key,
            openai_api_key: req.openai_api_key,
            ollama_base_url: req.ollama_base_url,
            harness_port: req.harness_port,
            vite_port: req.vite_port,
            state_db_path: req.state_db_path,
            log_dir: req.log_dir,
        }))
    }

    async fn restart_services(&self, _request: Request<RestartServicesRequest>) -> Result<Response<RestartServicesResponse>, Status> {
        Err(Status::unimplemented("RestartServices requires access to Tauri state. Use Tauri IPC for this specifically or wire state into the gRPC handler."))
    }
}
