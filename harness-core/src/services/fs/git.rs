use anyhow::{anyhow, Result};
use git2::{Repository, Signature, StatusOptions};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GitStatus {
    pub modified: Vec<String>,
    pub added: Vec<String>,
    pub deleted: Vec<String>,
    pub untracked: Vec<String>,
    pub branch: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GitBranch {
    pub name: String,
    pub is_current: bool,
    pub commit_sha: String,
}

pub async fn status(repo_path: &str) -> Result<GitStatus> {
    let repo_path = repo_path.to_string();
    tokio::task::spawn_blocking(move || -> Result<GitStatus> {
        let repo = Repository::open(&repo_path)?;
        let branch = repo
            .head()
            .ok()
            .and_then(|h| h.shorthand().map(str::to_string))
            .unwrap_or_else(|| "HEAD".into());

        let mut opts = StatusOptions::new();
        opts.include_untracked(true).recurse_untracked_dirs(true);
        let statuses = repo.statuses(Some(&mut opts))?;

        let mut modified = Vec::new();
        let mut added = Vec::new();
        let mut deleted = Vec::new();
        let mut untracked = Vec::new();

        for entry in statuses.iter() {
            let path = entry.path().unwrap_or("").to_string();
            let s = entry.status();
            if s.is_wt_new() && !s.is_index_new() {
                untracked.push(path);
            } else if s.is_index_new() || s.is_wt_new() {
                added.push(path);
            } else if s.is_index_deleted() || s.is_wt_deleted() {
                deleted.push(path);
            } else if s.is_index_modified() || s.is_wt_modified() {
                modified.push(path);
            }
        }

        Ok(GitStatus { modified, added, deleted, untracked, branch })
    })
    .await?
}

pub async fn diff(repo_path: &str) -> Result<String> {
    let repo_path = repo_path.to_string();
    tokio::task::spawn_blocking(move || -> Result<String> {
        let repo = Repository::open(&repo_path)?;
        let head = repo.head()?.peel_to_tree()?;
        let diff = repo.diff_tree_to_workdir_with_index(Some(&head), None)?;

        let mut output = Vec::new();
        diff.print(git2::DiffFormat::Patch, |_delta, _hunk, line| {
            use git2::DiffLineType::*;
            let prefix = match line.origin_value() {
                Addition => "+",
                Deletion => "-",
                _ => " ",
            };
            output.push(format!(
                "{}{}",
                prefix,
                std::str::from_utf8(line.content()).unwrap_or("")
            ));
            true
        })?;
        Ok(output.join(""))
    })
    .await?
}

pub async fn commit(repo_path: &str, message: &str, paths: Vec<String>) -> Result<String> {
    let repo_path = repo_path.to_string();
    let message = message.to_string();
    tokio::task::spawn_blocking(move || -> Result<String> {
        let repo = Repository::open(&repo_path)?;
        let mut index = repo.index()?;
        for p in &paths {
            index.add_path(std::path::Path::new(p))?;
        }
        index.write()?;
        let tree_id = index.write_tree()?;
        let tree = repo.find_tree(tree_id)?;
        let sig = Signature::now("Vloop Harness", "harness@local")?;
        let parents: Vec<git2::Commit> = repo
            .head()
            .ok()
            .and_then(|h| h.peel_to_commit().ok())
            .into_iter()
            .collect();
        let parent_refs: Vec<&git2::Commit> = parents.iter().collect();
        let oid = repo.commit(Some("HEAD"), &sig, &sig, &message, &tree, &parent_refs)?;
        Ok(oid.to_string())
    })
    .await?
}

pub async fn branches(repo_path: &str) -> Result<Vec<GitBranch>> {
    let repo_path = repo_path.to_string();
    tokio::task::spawn_blocking(move || -> Result<Vec<GitBranch>> {
        let repo = Repository::open(&repo_path)?;
        let current = repo
            .head()
            .ok()
            .and_then(|h| h.shorthand().map(str::to_string));

        let mut result = Vec::new();
        for b in repo.branches(Some(git2::BranchType::Local))? {
            let (branch, _) = b?;
            let name = branch.name()?.unwrap_or("").to_string();
            let sha = branch
                .get()
                .peel_to_commit()
                .map(|c| c.id().to_string())
                .unwrap_or_default();
            let is_current = current.as_deref() == Some(&name);
            result.push(GitBranch { name, is_current, commit_sha: sha });
        }
        Ok(result)
    })
    .await?
}
