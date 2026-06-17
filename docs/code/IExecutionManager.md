# IExecutionManager

## Overview
The Hexagonal Port defining execution boundaries.

## Responsibilities
- `dispatch_job(spec, policy) -> str`: Submits a job with a strict security policy.
- `stream_logs(job_id) -> Generator`: Yields real-time standard output/error.
- `teardown(job_id) -> None`: Forcefully destroys the execution environment.
