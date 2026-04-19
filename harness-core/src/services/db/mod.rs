pub mod models;
pub mod pool;

use anyhow::Result;
use pool::create_pool;
use sqlx::SqlitePool;
use std::path::PathBuf;

pub struct DbService {
    pub pool: SqlitePool,
}

impl DbService {
    pub async fn new() -> Result<Self> {
        let db_path = get_db_path();
        let pool = create_pool(&db_path).await?;
        Ok(Self { pool })
    }
}

fn get_db_path() -> PathBuf {
    let base = dirs_next::data_local_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("vloop-harness");
    std::fs::create_dir_all(&base).ok();
    base.join("harness.db")
}
