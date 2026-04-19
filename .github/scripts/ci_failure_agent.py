#!/usr/bin/env python3
"""Analyze failed CI workflow jobs and produce actionable fix suggestions."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

API_ROOT = "https://api.github.com"


def github_request(url: str, token: str) -> Any:
    req = Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            content_type = resp.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return json.loads(body)
            return body
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API request failed ({exc.code}) for {url}: {details}") from exc


def extract_workflow_excerpt(workflow_path: Path, job_name: str, context: int = 16) -> str:
    if not workflow_path.exists():
        return ""
    lines = workflow_path.read_text(encoding="utf-8").splitlines()
    needle = f"name: {job_name}"
    for i, line in enumerate(lines):
        if needle in line:
            start = max(0, i - context)
            end = min(len(lines), i + context + 1)
            numbered = [f"{idx + 1}: {txt}" for idx, txt in enumerate(lines[start:end], start=start)]
            return "\n".join(numbered)
    return ""


def list_referenced_paths(log_text: str, repo_root: Path) -> list[str]:
    refs: set[str] = set()
    for m in re.finditer(r"\bcd\s+([\w./-]+)", log_text):
        path = m.group(1).strip()
        if path.startswith("/"):
            continue
        candidate = repo_root / path
        if candidate.exists():
            refs.add(path)
    for m in re.finditer(r"([\w./-]+\.(?:yml|yaml|toml|json|lock|txt|py|rs|ts|tsx))", log_text):
        rel = m.group(1)
        if ".." in rel or rel.startswith("/"):
            continue
        if (repo_root / rel).exists():
            refs.add(rel)
    return sorted(refs)


def analyze_job_failure(job_name: str, log_text: str, workflow_excerpt: str, repo_root: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    lower = log_text.lower()

    if "npm ci" in lower and "can only install with an existing package-lock.json" in lower:
        lockfile = repo_root / "harness-ui" / "package-lock.json"
        has_lockfile = lockfile.exists()
        fix = (
            "Commit `harness-ui/package-lock.json` and keep using `npm ci` for deterministic installs."
            if not has_lockfile
            else "If lockfile exists, ensure workflow checks out the correct branch and lockfile is not excluded."
        )
        findings.append(
            {
                "title": "Node install failed due to missing lockfile",
                "evidence": "`npm ci` requires `package-lock.json`, but install step reports lockfile missing.",
                "fix": fix + " If lockfile is intentionally omitted, change workflow step to `npm install`.",
            }
        )

    if "modulenotfounderror" in lower or "no module named" in lower:
        findings.append(
            {
                "title": "Python dependency/module missing",
                "evidence": "Job logs contain `ModuleNotFoundError`/`No module named`.",
                "fix": "Add the missing package to the project dependency manifest (e.g., `pyproject.toml` or `requirements*.txt`), reinstall dependencies, and rerun tests.",
            }
        )

    if "pkg-config" in lower and ("was not found" in lower or "no package" in lower):
        findings.append(
            {
                "title": "Rust native system dependency missing",
                "evidence": "`pkg-config` failed to locate required native libraries for Rust crates.",
                "fix": "Install required Linux packages in the workflow before `cargo check` (e.g., GTK/WebKit/sqlite dev libs used by Tauri).",
            }
        )

    if not findings:
        err_lines = []
        for line in log_text.splitlines():
            line_stripped = line.strip()
            if re.search(r"\b(error|failed|exception|traceback)\b", line_stripped, flags=re.IGNORECASE):
                err_lines.append(line_stripped)
            if len(err_lines) >= 3:
                break
        evidence = "\n".join(err_lines) if err_lines else "No specific heuristic matched; inspect failed step logs."
        findings.append(
            {
                "title": "General CI failure",
                "evidence": evidence,
                "fix": "Reproduce locally using the same command as the failed workflow step, then update code/dependencies/workflow accordingly.",
            }
        )

    if workflow_excerpt:
        for finding in findings:
            finding["evidence"] += "\n\nWorkflow context:\n" + workflow_excerpt

    return findings


def build_markdown_report(
    repo: str,
    run_id: str,
    run_html_url: str,
    jobs: list[dict[str, Any]],
    analyses: list[dict[str, Any]],
) -> str:
    lines = [
        "# CI Failure Analysis Report",
        "",
        f"- Repository: `{repo}`",
        f"- Failed workflow run: [{run_id}]({run_html_url})",
        f"- Failed jobs analyzed: **{len(analyses)}**",
        "",
        "## Findings and Suggested Fixes",
        "",
    ]

    for job, analysis in zip(jobs, analyses):
        lines.append(f"### Job: {job.get('name', 'unknown')} (`{job.get('id')}`)")
        lines.append("")
        lines.append("**Traceability**")
        lines.append("")
        lines.append(f"- Job URL: {job.get('html_url', 'N/A')}")
        lines.append(f"- Conclusion: {job.get('conclusion', 'N/A')}")
        refs = analysis.get("referenced_paths", [])
        lines.append(f"- Referenced repository paths: {', '.join(f'`{p}`' for p in refs) if refs else 'None detected'}")
        lines.append("")
        for idx, finding in enumerate(analysis.get("findings", []), start=1):
            lines.append(f"{idx}. **{finding['title']}**")
            lines.append(f"   - Evidence: {finding['evidence']}")
            lines.append(f"   - Proposed fix: {finding['fix']}")
        lines.append("")

    lines.extend(
        [
            "## PR Suggestion",
            "",
            "Apply the proposed fix in a small PR, rerun the `CI` workflow, and attach this report to the PR description for auditability.",
            "",
        ]
    )

    return "\n".join(lines)


def main() -> int:
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPOSITORY")
    run_id = os.getenv("TARGET_RUN_ID")
    workflow_path_raw = os.getenv("TARGET_WORKFLOW_PATH", "")

    if not token or not repo or not run_id:
        print("Missing required environment variables: GITHUB_TOKEN, GITHUB_REPOSITORY, TARGET_RUN_ID", file=sys.stderr)
        return 2

    if "/" not in repo:
        print(f"Unexpected GITHUB_REPOSITORY format: {repo}", file=sys.stderr)
        return 2

    owner, name = repo.split("/", 1)
    repo_root = Path(os.getenv("GITHUB_WORKSPACE", ".")).resolve()

    workflow_rel = workflow_path_raw.split("@", 1)[0].strip()
    workflow_file = (repo_root / workflow_rel).resolve() if workflow_rel else Path("")

    run = github_request(f"{API_ROOT}/repos/{owner}/{name}/actions/runs/{run_id}", token)
    run_html_url = run.get("html_url", f"https://github.com/{repo}/actions/runs/{run_id}")

    jobs_payload = github_request(f"{API_ROOT}/repos/{owner}/{name}/actions/runs/{run_id}/jobs?per_page=100", token)
    failed_jobs = [
        j
        for j in jobs_payload.get("jobs", [])
        if j.get("conclusion") in {"failure", "timed_out", "cancelled", "action_required"}
    ]

    analyses: list[dict[str, Any]] = []
    for job in failed_jobs:
        logs = github_request(f"{API_ROOT}/repos/{owner}/{name}/actions/jobs/{job['id']}/logs", token)
        workflow_excerpt = extract_workflow_excerpt(workflow_file, job.get("name", "")) if workflow_file else ""
        findings = analyze_job_failure(job.get("name", ""), str(logs), workflow_excerpt, repo_root)
        analyses.append(
            {
                "job_id": job.get("id"),
                "job_name": job.get("name"),
                "findings": findings,
                "referenced_paths": list_referenced_paths(str(logs), repo_root),
            }
        )

    out_dir = repo_root / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "ci-failure-analysis.json"
    md_path = out_dir / "ci-failure-report.md"

    payload = {
        "repository": repo,
        "workflow_run_id": run_id,
        "workflow_run_url": run_html_url,
        "failed_jobs_count": len(failed_jobs),
        "analyses": analyses,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    report = build_markdown_report(repo, run_id, run_html_url, failed_jobs, analyses)
    md_path.write_text(report, encoding="utf-8")

    print(report)
    print(f"::notice title=CI failure report::{md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
