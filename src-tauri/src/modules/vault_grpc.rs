use tonic::{Request, Response, Status};

pub mod pb {
    tonic::include_proto!("vault");
}

use pb::vault_service_server::VaultService;
use pb::{
    ListKeysRequest, ListKeysResponse, SetKeyRequest, SetKeyResponse, DeleteKeyRequest, DeleteKeyResponse, VaultKey,
};

#[derive(Default)]
pub struct MyVaultService {}

#[tonic::async_trait]
impl VaultService for MyVaultService {
    async fn list_keys(&self, _request: Request<ListKeysRequest>) -> Result<Response<ListKeysResponse>, Status> {
        let keys = crate::modules::vault::get_all_keys();
        let mut vault_keys = Vec::new();
        for (k, v) in keys {
            vault_keys.push(VaultKey {
                key: k,
                value: v,
            });
        }
        Ok(Response::new(ListKeysResponse { keys: vault_keys }))
    }

    async fn set_key(&self, request: Request<SetKeyRequest>) -> Result<Response<SetKeyResponse>, Status> {
        let req = request.into_inner();
        crate::modules::vault::set_key(&req.key, &req.value);
        Ok(Response::new(SetKeyResponse { success: true }))
    }

    async fn delete_key(&self, request: Request<DeleteKeyRequest>) -> Result<Response<DeleteKeyResponse>, Status> {
        let req = request.into_inner();
        crate::modules::vault::delete_key(&req.key);
        Ok(Response::new(DeleteKeyResponse { success: true }))
    }
}
