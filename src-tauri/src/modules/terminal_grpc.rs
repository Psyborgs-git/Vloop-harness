use std::path::PathBuf;
use tonic::{Request, Response, Status};

pub mod pb {
    tonic::include_proto!("terminal");
}

use pb::terminal_service_server::TerminalService;
use pb::{
    ListSessionsRequest, ListSessionsResponse, StartSessionRequest, StartSessionResponse,
    WriteStdinRequest, WriteStdinResponse, ReadBufferRequest, ReadBufferResponse,
    CloseSessionRequest, CloseSessionResponse, KillAllSessionsRequest, KillAllSessionsResponse,
};

#[derive(Default)]
pub struct MyTerminalService {}

#[tonic::async_trait]
impl TerminalService for MyTerminalService {
    async fn list_sessions(&self, _request: Request<ListSessionsRequest>) -> Result<Response<ListSessionsResponse>, Status> {
        let sessions = crate::modules::terminal::list_sessions();
        Ok(Response::new(ListSessionsResponse { session_ids: sessions }))
    }

    async fn start_session(&self, request: Request<StartSessionRequest>) -> Result<Response<StartSessionResponse>, Status> {
        let req = request.into_inner();
        let repo_root = crate::modules::main::get_repo_root();
        let data_dir = crate::modules::main::get_data_dir(&repo_root);
        let timestamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs();
        let log_file_path = data_dir.join("rust").join("terminal").join(format!("{}.logs", timestamp));
        let cwd_path = PathBuf::from(req.cwd);
        
        match crate::modules::terminal::start_local_session(req.session_id, cwd_path, req.command, req.args, log_file_path).await {
            Ok(_) => Ok(Response::new(StartSessionResponse { success: true, error_message: String::new() })),
            Err(e) => Ok(Response::new(StartSessionResponse { success: false, error_message: e })),
        }
    }

    async fn write_stdin(&self, request: Request<WriteStdinRequest>) -> Result<Response<WriteStdinResponse>, Status> {
        let req = request.into_inner();
        match crate::modules::terminal::send_keys(&req.session_id, &req.data) {
            Ok(_) => Ok(Response::new(WriteStdinResponse { success: true, error_message: String::new() })),
            Err(e) => Ok(Response::new(WriteStdinResponse { success: false, error_message: e })),
        }
    }

    async fn read_buffer(&self, request: Request<ReadBufferRequest>) -> Result<Response<ReadBufferResponse>, Status> {
        let req = request.into_inner();
        match crate::modules::terminal::read_buffer(&req.session_id) {
            Ok(data) => Ok(Response::new(ReadBufferResponse { success: true, data, error_message: String::new() })),
            Err(e) => Ok(Response::new(ReadBufferResponse { success: false, data: String::new(), error_message: e })),
        }
    }

    async fn close_session(&self, request: Request<CloseSessionRequest>) -> Result<Response<CloseSessionResponse>, Status> {
        let req = request.into_inner();
        match crate::modules::terminal::close_session(&req.session_id) {
            Ok(_) => Ok(Response::new(CloseSessionResponse { success: true, error_message: String::new() })),
            Err(e) => Ok(Response::new(CloseSessionResponse { success: false, error_message: e })),
        }
    }

    async fn kill_all_sessions(&self, _request: Request<KillAllSessionsRequest>) -> Result<Response<KillAllSessionsResponse>, Status> {
        crate::modules::terminal::kill_all_sessions();
        Ok(Response::new(KillAllSessionsResponse { success: true }))
    }
}
