from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / ".github" / "scripts" / "ci_failure_agent.py"
    spec = spec_from_file_location("ci_failure_agent", script_path)
    module = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_detects_missing_npm_lockfile(tmp_path: Path):
    module = _load_module()
    repo = tmp_path
    (repo / "harness-ui").mkdir(parents=True)
    findings = module.analyze_job_failure(
        "TypeScript (tsc)",
        "npm error The `npm ci` command can only install with an existing package-lock.json",
        "",
        repo,
    )
    assert findings[0]["title"] == "Node install failed due to missing lockfile"
    assert "package-lock.json" in findings[0]["fix"]


def test_detects_python_module_error(tmp_path: Path):
    module = _load_module()
    findings = module.analyze_job_failure(
        "Python (pytest)",
        "ModuleNotFoundError: No module named 'fastapi'",
        "",
        tmp_path,
    )
    assert findings[0]["title"] == "Python dependency/module missing"


def test_detects_rust_pkg_config_error(tmp_path: Path):
    module = _load_module()
    findings = module.analyze_job_failure(
        "Rust (cargo check)",
        "pkg-config output: Package glib-2.0 was not found in the pkg-config search path",
        "",
        tmp_path,
    )
    assert findings[0]["title"] == "Rust native system dependency missing"


def test_lists_referenced_paths(tmp_path: Path):
    module = _load_module()
    (tmp_path / "harness-ui").mkdir()
    (tmp_path / "harness-ui" / "package.json").write_text("{}", encoding="utf-8")
    refs = module.list_referenced_paths("cd harness-ui && npm install uses harness-ui/package.json", tmp_path)
    assert "harness-ui" in refs
    assert "harness-ui/package.json" in refs
