use tonic::{Request, Response, Status};

pub mod pb {
    tonic::include_proto!("sandbox");
}

use pb::sandbox_service_server::SandboxService;
use pb::{ProvisionRequest, ProvisionResponse, TeardownRequest, TeardownResponse};

#[derive(Default)]
pub struct MySandboxService {}

#[tonic::async_trait]
impl SandboxService for MySandboxService {
    async fn provision(
        &self,
        request: Request<ProvisionRequest>,
    ) -> Result<Response<ProvisionResponse>, Status> {
        let _req = request.into_inner();
        // Implement actual provisioning logic using terminal/sandbox module
        
        Ok(Response::new(ProvisionResponse {
            success: true,
            error_message: String::new(),
        }))
    }

    async fn teardown(
        &self,
        request: Request<TeardownRequest>,
    ) -> Result<Response<TeardownResponse>, Status> {
        let _req = request.into_inner();
        
        Ok(Response::new(TeardownResponse {
            success: true,
            error_message: String::new(),
        }))
    }


}

#[cfg(test)]
mod tests {
    use super::*;
    use tonic::Request;
    use pb::SandboxConfig;

    #[tokio::test]
    async fn test_provision() {
        let service = MySandboxService::default();
        let config = SandboxConfig {
            r#type: pb::sandbox_config::Type::Local as i32,
            image: String::new(),
            host: String::new(),
            user: String::new(),
            command: "echo".to_string(),
            args: vec!["test".to_string()],
            cwd: String::new(),
        };

        let req = Request::new(ProvisionRequest {
            session_id: "test-session-123".to_string(),
            config: Some(config),
        });

        let res = service.provision(req).await.unwrap();
        assert!(res.into_inner().success);
    }

    #[tokio::test]
    async fn test_teardown() {
        let service = MySandboxService::default();
        let req = Request::new(TeardownRequest {
            session_id: "test-session-123".to_string(),
        });

        let res = service.teardown(req).await.unwrap();
        assert!(res.into_inner().success);
    }
}
