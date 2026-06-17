# PolicyGenerator

## Overview
A DSPy Module responsible for security static analysis.

## Responsibilities
- Utilizes the `PolicyGenerationSignature` (`python_code` -> `security_policy_json`).
- Parses LLM output to extract a JSON dictionary defining if the generated code actually requires `network` or `volume_mount` capabilities.
- Defaults to a fail-closed strict policy if parsing fails.
