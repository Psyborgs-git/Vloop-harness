# Troubleshooting

### Issue: Backend port already in use
**Symptoms**: `Backend port conflict` during service start.
**Cause**: Another process is listening on `HARNESS_PORT`.
**Fix**: Stop conflicting process or set a new `HARNESS_PORT` in `.env`.
**Prevention**: Reserve standard local ports per project.

### Issue: Frontend port already in use
**Symptoms**: Frontend fails to start; Vite reports port conflict.
**Cause**: Existing process bound to `VITE_PORT`.
**Fix**: Change `VITE_PORT` or stop conflicting process.
**Prevention**: Run `harness services status` before startup.

### Issue: Vite dev server unreachable
**Symptoms**: `/ui/root` returns 503 in debug mode.
**Cause**: Frontend process not running or crashed.
**Fix**: `cd react && npm install && npm run dev` or restart services.
**Prevention**: Ensure frontend dependencies are installed.

### Issue: Static mode missing dist assets
**Symptoms**: 503 mentions missing `react/dist` or entry HTML.
**Cause**: Static mode enabled without build artifacts.
**Fix**: `cd react && npm run build`; then rerun with static mode.
**Prevention**: Build frontend before static deployments.

### Issue: AI engine not configured
**Symptoms**: Chat or view generation says engine/provider not configured.
**Cause**: No default provider configured in DB.
**Fix**: Create provider via Settings API/UI and set as default.
**Prevention**: Configure provider during initial setup.

### Issue: Provider connectivity test fails
**Symptoms**: `/api/providers/{id}/test` returns error.
**Cause**: Invalid API key/model/base URL or network issue.
**Fix**: Verify credentials and endpoint; retry test.
**Prevention**: Validate keys externally and store correct base URLs.

### Issue: Tool action blocked by policy
**Symptoms**: Tool endpoint returns policy error.
**Cause**: Denylist/blocklist/workspace policy restriction.
**Fix**: Review `/api/tools/policy` and adjust if allowed by team rules.
**Prevention**: Define project policy up front.

### Issue: Tool action requires confirmation
**Symptoms**: HTTP 202 with `requires_confirmation=true`.
**Cause**: Risky action guard triggered.
**Fix**: Confirm with `POST /api/tools/confirm/{token}`.
**Prevention**: Expect confirmation on destructive writes/deletes.

### Issue: Component compile errors (DSPy)
**Symptoms**: 422 on component create/update/run.
**Cause**: Invalid generated/manual component code.
**Fix**: Inspect returned compile error detail; fix signature/module code.
**Prevention**: Keep component code minimal and test compile early.

### Issue: WebSocket closes with component not found
**Symptoms**: WS close code 4004 for `/ws/{component_id}`.
**Cause**: Component was removed/unregistered.
**Fix**: Recreate component or refresh to current component IDs.
**Prevention**: Handle component lifecycle changes in UI.

### Issue: SQLite write/lock failures
**Symptoms**: DB operation errors under `.vloop`.
**Cause**: Permission issues or concurrent file locks.
**Fix**: Ensure writable workspace, stop duplicate harness instances.
**Prevention**: Run a single local backend per workspace.

### Issue: Playwright tests fail to launch browser
**Symptoms**: `browser executable not found` in e2e tests.
**Cause**: Browser binaries unavailable at configured path.
**Fix**: Install browsers (`npx playwright install`) or set `PLAYWRIGHT_BROWSERS_PATH` correctly.
**Prevention**: Validate browser installation after dependency install.
