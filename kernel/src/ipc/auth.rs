use tonic::{metadata::MetadataMap, Request, Status};
use uuid::Uuid;

pub const REQUEST_ID_HEADER: &str = "x-vloop-request-id";
pub const BOOTSTRAP_TOKEN_HEADER: &str = "x-vloop-bootstrap-token";
pub const SESSION_ID_HEADER: &str = "x-vloop-session-id";

pub fn generate_bootstrap_token() -> String {
    Uuid::new_v4().to_string()
}

pub fn new_request<T>(message: T) -> Request<T> {
    let mut request = Request::new(message);
    attach_request_id(request.metadata_mut());
    request
}

pub fn new_bootstrap_request<T>(message: T, bootstrap_token: &str) -> Request<T> {
    let mut request = new_request(message);
    request.metadata_mut().insert(
        BOOTSTRAP_TOKEN_HEADER,
        bootstrap_token.parse().expect("valid bootstrap token"),
    );
    request
}

pub fn new_session_request<T>(message: T, session_id: &str) -> Request<T> {
    let mut request = new_request(message);
    request.metadata_mut().insert(
        SESSION_ID_HEADER,
        session_id.parse().expect("valid session id"),
    );
    request
}

pub fn require_request_id(metadata: &MetadataMap) -> Result<String, Status> {
    header_value(metadata, REQUEST_ID_HEADER)
        .ok_or_else(|| Status::invalid_argument("missing x-vloop-request-id metadata"))
}

pub fn require_bootstrap_token(metadata: &MetadataMap, expected: &str) -> Result<(), Status> {
    let provided = header_value(metadata, BOOTSTRAP_TOKEN_HEADER)
        .ok_or_else(|| Status::unauthenticated("missing bootstrap token metadata"))?;

    if provided != expected {
        return Err(Status::unauthenticated("invalid bootstrap token"));
    }

    Ok(())
}

pub fn require_session_id(metadata: &MetadataMap, expected: &str) -> Result<(), Status> {
    let provided = header_value(metadata, SESSION_ID_HEADER)
        .ok_or_else(|| Status::unauthenticated("missing session id metadata"))?;

    if provided != expected {
        return Err(Status::unauthenticated("invalid session id"));
    }

    Ok(())
}

pub fn maybe_session_id(metadata: &MetadataMap) -> Option<String> {
    header_value(metadata, SESSION_ID_HEADER)
}

fn attach_request_id(metadata: &mut MetadataMap) {
    metadata.insert(
        REQUEST_ID_HEADER,
        Uuid::new_v4()
            .to_string()
            .parse()
            .expect("valid request id"),
    );
}

fn header_value(metadata: &MetadataMap, key: &str) -> Option<String> {
    metadata
        .get(key)
        .and_then(|value| value.to_str().ok())
        .map(str::to_string)
}
