use crate::rpc::system::system_control_client::SystemControlClient;
use crate::rpc::system::system_control_server::{SystemControl, SystemControlServer};
use crate::rpc::system::infrastructure_control_server::InfrastructureControlServer;
use crate::infra::InfraService;
use crate::rpc::system::{
    HeartbeatRequest, HeartbeatResponse, IngestRequest, IngestResponse, Ping, Pong, ReloadRequest,
    ReloadResponse, RewindRequest, RewindResponse, SwarmRequest, TaskRequest, TaskResponse,
    WorkflowStateRequest, WorkflowStateResponse,
};
use std::sync::Arc;
use tokio::sync::Mutex;
use tonic::{transport::Server, Request, Response, Status};

pub struct SwarmService {
    client: Arc<Mutex<Option<SystemControlClient<tonic::transport::Channel>>>>,
}

#[tonic::async_trait]
impl SystemControl for SwarmService {
    async fn health_check(&self, req: Request<Ping>) -> Result<Response<Pong>, Status> {
        let mut client = self.get_client().await?;
        client.health_check(req).await
    }

    async fn reload_config(&self, req: Request<ReloadRequest>) -> Result<Response<ReloadResponse>, Status> {
        let mut client = self.get_client().await?;
        client.reload_config(req).await
    }

    async fn dispatch_task(&self, req: Request<TaskRequest>) -> Result<Response<TaskResponse>, Status> {
        let mut client = self.get_client().await?;
        client.dispatch_task(req).await
    }

    async fn heartbeat(&self, req: Request<HeartbeatRequest>) -> Result<Response<HeartbeatResponse>, Status> {
        let mut client = self.get_client().await?;
        client.heartbeat(req).await
    }

    async fn rewind_workspace(&self, req: Request<RewindRequest>) -> Result<Response<RewindResponse>, Status> {
        let mut client = self.get_client().await?;
        client.rewind_workspace(req).await
    }

    async fn ingest_document(&self, req: Request<IngestRequest>) -> Result<Response<IngestResponse>, Status> {
        let mut client = self.get_client().await?;
        client.ingest_document(req).await
    }

    async fn swarm_task(&self, req: Request<SwarmRequest>) -> Result<Response<TaskResponse>, Status> {
        let mut client = self.get_client().await?;
        client.swarm_task(req).await
    }

    async fn get_workflow_state(&self, req: Request<WorkflowStateRequest>) -> Result<Response<WorkflowStateResponse>, Status> {
        let mut client = self.get_client().await?;
        client.get_workflow_state(req).await
    }

    async fn notify_user_action(&self, req: Request<crate::rpc::system::UserActionRequest>) -> Result<Response<crate::rpc::system::UserActionResponse>, Status> {
        let mut client = self.get_client().await?;
        client.notify_user_action(req).await
    }
}

impl SwarmService {
    async fn get_client(&self) -> Result<SystemControlClient<tonic::transport::Channel>, Status> {
        let mut lock = self.client.lock().await;
        if let Some(c) = lock.as_ref() {
            return Ok(c.clone());
        }

        let vloop_home = crate::fs::get_vloop_home()
            .ok_or_else(|| Status::internal("Failed to get vloop home"))?;
        let socket_path = vloop_home.join("rust").join("ipc.sock");

        #[cfg(unix)]
        let channel = {
            tonic::transport::Endpoint::try_from("http://[::]:50051")
                .unwrap()
                .connect_with_connector(tower::service_fn(move |_: tonic::transport::Uri| {
                    let path = socket_path.clone();
                    async move {
                        Ok::<_, std::io::Error>(hyper_util::rt::TokioIo::new(
                            tokio::net::UnixStream::connect(path).await?,
                        ))
                    }
                }))
                .await
                .map_err(|e| Status::internal(e.to_string()))?
        };

        #[cfg(not(unix))]
        let channel = tonic::transport::Endpoint::try_from("http://127.0.0.1:50051")
            .unwrap()
            .connect()
            .await
            .map_err(|e| Status::internal(e.to_string()))?;

        let client = SystemControlClient::new(channel);
        *lock = Some(client.clone());
        Ok(client)
    }
}

pub fn start_swarm_listener() {
    tokio::spawn(async move {
        println!("Starting Swarm & Infra TCP Listener on 0.0.0.0:50052...");
        let addr = "0.0.0.0:50052".parse().unwrap();
        let service = SwarmService {
            client: Arc::new(Mutex::new(None)),
        };
        let infra_service = InfraService {};

        if let Err(e) = Server::builder()
            .add_service(SystemControlServer::new(service))
            .add_service(InfrastructureControlServer::new(infra_service))
            .serve(addr)
            .await
        {
            eprintln!("Swarm/Infra TCP listener failed: {}", e);
        }
    });
}