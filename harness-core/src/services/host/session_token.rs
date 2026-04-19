use anyhow::{anyhow, Result};
use chrono::{Duration, Utc};
use hmac::{Hmac, Mac};
use rand::Rng;
use sha2::Sha256;
use std::collections::HashMap;
use uuid::Uuid;

type HmacSha256 = Hmac<Sha256>;

/// Generate an HMAC-SHA256 signed session token.
/// Payload: `ip:iat:exp:nonce`
pub fn generate_token(
    secret: &[u8],
    client_ip: &str,
    ttl_minutes: i64,
) -> Result<String> {
    let nonce = Uuid::new_v4().to_string();
    let iat = Utc::now().timestamp();
    let exp = (Utc::now() + Duration::minutes(ttl_minutes)).timestamp();
    let payload = format!("{client_ip}:{iat}:{exp}:{nonce}");

    let mut mac = HmacSha256::new_from_slice(secret)
        .map_err(|e| anyhow!("HMAC key error: {e}"))?;
    mac.update(payload.as_bytes());
    let result = mac.finalize().into_bytes();

    let sig = hex::encode(result);
    let token = format!("{payload}.{sig}");
    Ok(token)
}

/// Verify a token: check HMAC, expiry, and (optionally) IP match.
pub fn verify_token(secret: &[u8], token: &str, client_ip: &str) -> Result<()> {
    let (payload, sig) = token
        .rsplit_once('.')
        .ok_or_else(|| anyhow!("Malformed token"))?;

    let mut mac = HmacSha256::new_from_slice(secret)
        .map_err(|e| anyhow!("HMAC key error: {e}"))?;
    mac.update(payload.as_bytes());
    let expected = hex::encode(mac.finalize().into_bytes());
    if expected != sig {
        return Err(anyhow!("Invalid token signature"));
    }

    let parts: Vec<&str> = payload.split(':').collect();
    if parts.len() < 4 {
        return Err(anyhow!("Malformed token payload"));
    }

    let token_ip = parts[0];
    let exp: i64 = parts[2].parse().map_err(|_| anyhow!("Invalid exp"))?;

    if Utc::now().timestamp() > exp {
        return Err(anyhow!("Token expired"));
    }
    if token_ip != client_ip {
        return Err(anyhow!("IP mismatch"));
    }

    Ok(())
}
