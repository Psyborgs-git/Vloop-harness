# **VLoop v1.2: Complete Advanced Orchestration Blueprint**

**Status:** Architecture Finalization

**Objective:** Evolve the stateless DSPy orchestrator into a durable, multi-agent workflow engine capable of metaprogramming, serving mini-apps, and hijacking 3rd-party coding harnesses via strictly isolated boundaries.

## **1\. Durable Workflow Engine (DAG)**

Python asyncio is volatile. Long-running tasks die when the OS sleeps or the daemon restarts.

* **The Architecture:**  
  * Introduce a SQLite-backed Directed Acyclic Graph (DAG) state tracker.  
  * When DSPy breaks a goal into sub-tasks, it compiles them into a DAG and commits the graph to IRelationalDB (\~/.vloop/control-plane/db/workflows.db).  
  * **Execution:** The CP reads the next pending node, dispatches it to a sandbox, and suspends.  
  * **Recovery:** If the Rust microkernel reboots the Python CP, the CP queries the DB, finds the last PENDING or RUNNING node, and resumes. Zero state loss.

## **2\. Coding Harness Adapters (ICodingHarness)**

Do not build custom bash loops. Wrap existing open-source coding agents as hexagonal execution adapters.

* **The Interface:**  
  * AiderAdapter (CLI/lightweight)  
  * OpenHandsAdapter (Containerized/heavyweight)  
* **Volume-Mapped State (Git as API):**  
  * Rust provisions \~/.vloop/control-plane/workspaces/{task\_id}/ on the host.  
  * This directory is bind-mounted into the harness sandbox.  
  * Harnesses are prompted to strictly git commit all work.  
  * The CP evaluates output by reading git diff and git log directly from the host filesystem. No stdout parsing required for code extraction.

## **3\. LLM Hijacking & Token Budgeting (Local Proxy)**

Third-party harnesses cannot be trusted with raw API keys. They will burn your budget or leak credentials.

* **The Architecture:**  
  * Python CP boots a local LiteLLM Proxy Server (e.g., localhost:4000 on the host).  
  * Rust configures the sandbox network bridge (e.g., routing 10.0.2.2 to the host) and injects environment variables: OPENAI\_API\_BASE=http://\<bridge\_ip\>:4000/v1 and a dummy API key.  
  * **The Trap:** The harness thinks it is talking to OpenAI. It is actually routing through the DSPy CP.  
  * **The Kill Switch:** The CP tracks token burn per DAG node. If the harness exceeds the budget, the CP severs the proxy connection and commands Rust to nuke the sandbox.

## **4\. Ephemeral Mini-Apps (Sandboxed UIs)**

When a task results in a dashboard or web tool, raw JSON is insufficient.

* **The Architecture:**  
  * The CP instructs an agent to write a single-file web app (FastHTML, Streamlit, Gradio).  
  * The script is executed in a dedicated "UI Sandbox".  
  * Rust maps a dynamic host port (e.g., 8501\) to the sandbox's internal port.  
  * Rust sends an IPC event to Tauri: {"action": "mount\_ui", "url": "http://localhost:8501"}.  
  * Tauri dynamically spawns a WebView/iframe tab.  
  * When the user closes the tab in Tauri, Rust terminates the UI Sandbox instantly.

## **5\. Metaprogramming (Nested DSPy Execution)**

The Core Control Plane must remain immutable. It cannot evaluate generated orchestration code on its own event loop without risking a fatal crash.

* **The Architecture:**  
  * If the Core CP determines it needs a custom DSPy Signature or Optimizer, it generates the Python script.  
  * The script is saved to \~/.vloop/control-plane/generated\_modules/.  
  * The Core CP dispatches a command to Rust to boot a **Worker Sandbox** containing the DSPy runtime.  
  * The Worker Sandbox executes the custom DSPy logic, connects to the local LiteLLM proxy, outputs the result to the volume mount, and dies.  
  * The Core CP reads the result. System stability remains 100%.

## **6\. End-to-End Advanced Execution Flow**

**Scenario:** User requests: *"Analyze this CSV, build a data cleaning pipeline, and give me a dashboard to view the anomalies."*

1. **DAG Generation:** Core DSPy CP processes the prompt and generates a 3-node DAG (1. Code Pipeline, 2\. Execute Pipeline, 3\. Serve UI). Commits to SQLite.  
2. **Node 1 (Harness):** CP mounts the CSV to a workspace volume and invokes AiderAdapter.  
3. **Hijack & Monitor:** Aider boots in a sandbox, writes the cleaning script, testing against the LiteLLM proxy. CP monitors tokens. Aider finishes and commits to Git. Sandbox destroyed. Node 1 marked COMPLETE.  
4. **Node 2 (Worker Execution):** CP reads the Git diff, validates the Python script. Dispatches the script to a vanilla Worker Sandbox to process the massive CSV. Outputs cleaned\_data.csv to the volume. Sandbox destroyed. Node 2 marked COMPLETE.  
5. **Node 3 (Mini-App):** CP generates a FastHTML script pointing to cleaned\_data.csv. Dispatches to a UI Sandbox.  
6. **Delivery:** Rust maps the port, signals Tauri. Tauri opens the dashboard. Node 3 marked COMPLETE.