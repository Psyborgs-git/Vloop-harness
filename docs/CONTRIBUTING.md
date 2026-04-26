# Contributing

## Development Workflow

### Branching Strategy
- Main branch: `main`.
- Branch naming:
  - `feature/<ticket-id>-short-description`
  - `fix/<ticket-id>-what-is-fixed`
  - `chore/<short-description>`
- `main` is the protected branch: no direct pushes; all changes flow through reviewed PRs.
- Rebase or merge from `main` before opening PR to reduce drift.

### Commit Standards
Use Conventional Commits:
```text
type(scope): short description
```
Allowed types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `perf`, `ci`.
Rules:
- Imperative mood.
- Subject <= 72 chars.
- Include ticket/reference ID in body/footer when available.

### Pull Request Process
1. Branch from `main`.
2. Implement code + tests.
3. Run local checks (pytest + relevant frontend checks).
4. Self-review diff for safety/security/policy implications.
5. Open PR with clear summary and validation notes.
6. Obtain at least 1 reviewer approval before merge.
7. Ensure local verification checks pass (Python tests, lint/type checks, and relevant frontend checks) since CI workflow files are not currently in-repo.
8. Merge strategy: squash merge preferred for clean history.
9. Delete branch after merge.

### PR Checklist
- [ ] Tests written and passing
- [ ] No regressions in existing tests
- [ ] Linting passes
- [ ] Types are correct (Python + TypeScript where relevant)
- [ ] No debug code/log noise left behind
- [ ] Env vars documented if added
- [ ] Breaking changes noted

## Code Standards

### General Principles
- Prefer readability over cleverness.
- Keep route handlers thin; business/data logic belongs in engine/repository layers.
- Fail explicitly with meaningful errors.
- Preserve auditability for agent/tool actions.

### File & Naming Conventions
- Python modules: `snake_case.py`.
- Python classes: `PascalCase`.
- Functions/variables: `snake_case`.
- TS/React components: `PascalCase.tsx`.
- Route files grouped by feature under `harness/server/routes/`.

### Where Code Goes
- API contracts/serialization: `harness/server/routes/`.
- Persistent model changes: `harness/data/models.py` + `harness/data/repository.py`.
- Runtime orchestration changes: `harness/core/` or `harness/engine/`.
- Tool additions: `harness/tools/` and register in `MainProcess.boot()`.

### Error Handling
- Use `HTTPException` in routes for expected request errors.
- Convert lower-level exceptions into actionable API errors.
- Avoid swallowing exceptions unless deliberately non-critical (and comment why).

### Logging
- Use structured logging paths already provided by harness logger/storage.
- Log operation intent + identifiers (run_id, component_id) without secrets.
- Never log API keys, tokens, or sensitive prompt data unless redacted.

## Testing Requirements

### Coverage Expectations
- No explicit global threshold configured; expectation is meaningful coverage for changed behavior.
- Must test route behavior, persistence changes, and tool/policy safety paths for modified code.

### Test Structure
- Python tests live in `tests/` as `test_*.py`.
- Prefer descriptive names: `test_<unit>_<expected_behavior>`.
- Suggested pattern:
```python
describe("[unit under test]", () => {
  it("should [behavior] when [condition]", () => { ... })
})
```
(Equivalent style in pytest naming/structure.)

### Test Types
- **Unit**: core helpers, policy checks, repository methods.
- **Integration**: FastAPI route interactions with DB/session fixtures.
- **E2E**: Playwright scenarios under `react/tests/e2e`.

## Code Review Standards
- Reviewers check correctness, safety, readability, test depth, and architectural fit.
- Blocking comments: correctness bugs, unsafe tool access, missing tests, broken contracts.
- Non-blocking comments: style nits, optional refactors.
- Author response SLA: acknowledge review feedback within 1 business day and resolve blocking comments before merge.

## Release Process
- Version values currently appear in `pyproject.toml` (`0.1.0`) and API metadata/UI package (`0.2.0`); reconcile before formal release.
- Release approval owner: repository maintainers responsible for `main` merges and release tagging.
- Update `docs/CHANGELOG.md` on release cut.
