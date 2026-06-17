# **VLoop v1.3: Swarm Execution, Time-Travel, & UI/UX Specs**

**Status:** Roadmap & UI Definition

## **Part 1: V1.3 Feature Upgrades**

### **1\. Peer-to-Peer Swarm Execution (Distributed VLoop)**

**The Reality:** A single machine hits hardware limits. You have a laptop, a desktop, and an AWS instance. They should share the load seamlessly.

**The Upgrade:**

* **Rust P2P Mesh:** Rust nodes discover each other via a local network mesh or a defined static IP list.  
* **DAG Task Stealing:** The Python CP's SQLite DAG becomes aware of the swarm. If your laptop's CPU is pegged, the Rust microkernel securely tunnels the workload (Git repo \+ sandbox spec) to your idle desktop.  
* **Unified State:** Artifacts and Git diffs are synced back to the originating machine upon completion. You orchestrate on the laptop; the heavy lifting happens on the desktop.

### **2\. DAG Time-Travel & Branching (State Reversion)**

**The Reality:** Agents hallucinate. If a 10-step DAG fails at Step 8, restarting from Step 1 wastes time and tokens.

**The Upgrade:**

* Because state is durable (SQLite) and artifacts are versioned (Git), you can implement time-travel.  
* When a node fails, the UI allows you to "Rewind" to Step 7\.  
* Rust executes a hard git reset \--hard on the workspace volume to the exact commit mapped to Step 7\.  
* The Python CP deletes SQLite DAG nodes 8-10, allows you to edit the prompt/logic, and forks the execution path.

### **3\. Continuous Background RAG (The Context Daemon)**

**The Reality:** Forcing the user to manually upload files or point to repos for every task is tedious.

**The Upgrade:**

* A low-priority Rust background thread continuously indexes specified host directories (e.g., \~/Projects).  
* It chunks, embeds, and pushes code/documents to the local Chroma/pgvector adapter *before* you even ask a question.  
* When you trigger a harness, the DSPy orchestrator already has the entire semantic map of your local machine.

## **Part 2: UI/UX Design Philosophy**

Forget the hacker aesthetic. The goal is friction-free mainstream adoption. The UI must feel approachable and safe for non-technical users while hiding an industrial-grade engine underneath.

### **1\. Core Principles**

* **Progressive Disclosure:** Complexity is opt-in. Default to showing high-level, human-readable summaries. Hide the raw LiteLLM proxy logs, Docker commands, and Git diffs behind a "Developer Mode" or "Advanced" toggle.  
* **Consumer-Grade Aesthetics:** Clean, modern, and breathable interfaces (e.g., Vercel, Linear, Notion). Use soft rounded corners, subtle shadows, and clear visual hierarchies.  
* **Omnimodal Navigation:** Maintain the Command Palette (Cmd+K) for power users, but ensure every core action is achievable via intuitive mouse clicks, drag-and-drop, and clear button labels.  
* **Curated Transparency:** Instead of a chaotic token ticker, use humanized state indicators. Show what the agent is actually doing: *"Analyzing requirements,"* *"Writing tests,"* *"Fixing syntax errors,"* alongside a simple, clean progress bar.

### **2\. Visual Language**

* **Palette:** Crisp whites or soft dark modes (e.g., \#121212), muted grays for borders, and soft accent colors for status.  
  * *Blue/Purple:* Active AI generation or thought process.  
  * *Green:* Task successfully completed.  
  * *Amber:* User input required (HITL approval).  
  * *Red:* Hard failure requiring user intervention.  
* **Typography:** Clean sans-serif fonts like Inter or Geist for all UI elements. Limit monospace fonts (JetBrains Mono) strictly to code blocks and the Developer Mode terminal.

## **Part 3: Layout & Views**

The Tauri app operates as a split-pane canvas. It guides the user visually from the high-level goal down to the specific output, without overwhelming them.

### **1\. The Global Header**

* Contains the **Omnibar (Cmd/Ctrl \+ K)** for quick actions.  
* Displays a simple, non-intrusive session cost metric (e.g., "Current Session: $0.42").  
* Houses the critical **"Developer Mode" Toggle**. Flipping this entirely changes the data density of the app for technical debugging.

### **2\. The Workflow Canvas (Main Pane \- 60%)**

* A friendly, interactive drag-and-drop node visualizer for the DAG.  
* **Default View:** Nodes look like clean task cards. They show a title ("Build Login Page"), a status icon, and a short summary of the agent's progress.  
* **Interaction:** Users can click a node to view its output, drag lines to create dependencies, or hit a simple "Rewind" button on a failed node to trigger the Time-Travel feature.

### **3\. The Execution Feed (Right Pane \- 40%)**

This pane dynamically updates based on the selected node.

* **Default View (Human-Readable):** \* Functions like a clean chat interface or activity feed.  
  * "Agent successfully wrote auth.py."  
  * "Agent encountered a bug, attempting to fix..."  
  * Shows the final Mini-App UI (WebView) directly in this pane when a "Serve UI" node completes.  
* **Advanced View (When 'Developer Mode' is ON):**  
  * The feed flips to a tabbed interface for power users.  
  * **Tab 1 \- Proxy Intercept:** Raw JSON payloads and token burns between DSPy and the LiteLLM gateway.  
  * **Tab 2 \- Workspace Diff:** Live git diff outputs of what the sandboxed harness is actively changing on the filesystem.  
  * **Tab 3 \- Sandbox Logs:** Raw stderr/stdout from the Firecracker VM or Docker container.

### **4\. Configuration & Settings (Modal Overlays)**

* Do not clutter the main view with database connection strings.  
* Settings like "Vector DB Provider," "Local vs AWS Sandbox," and "LLM API Keys" live in clean, structured modal menus.  
* Use sensible defaults out-of-the-box (SQLite \+ Local Docker/MicroVM) so the user doesn't have to configure anything to run their first task.