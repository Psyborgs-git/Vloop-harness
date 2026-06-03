# Getting Started with VLoop Harness

Welcome to VLoop Harness! This guide will help you get up and running with the AI agent development platform.

## Prerequisites

- Python 3.11 or higher
- Node.js 18 or higher
- npm or bun
- Git

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/Vloop-harness.git
cd Vloop-harness
```

### 2. Install Backend Dependencies

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .
```

### 3. Install Frontend Dependencies

```bash
cd react
npm install
# or with bun
bun install
```

### 4. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your settings
# - AI provider API keys
# - Database configuration
# - Server settings
```

## Starting the System

### Development Mode

#### Terminal 1 - Start Backend
```bash
cd /path/to/Vloop-harness
source .venv/bin/activate
python -m harness.main
```

#### Terminal 2 - Start Frontend
```bash
cd /path/to/Vloop-harness/react
npm run dev
```

The dashboard will be available at `http://localhost:5173`

### Production Mode

See [Operator Runbook](OPERATOR_RUNBOOK.md) for production deployment instructions.

## First Steps

### 1. Configure an AI Provider

Before you can use VLoop Harness, you need to configure at least one AI provider.

1. Open the dashboard at `http://localhost:5173`
2. Click the Settings (⚙) icon in the top right
3. Navigate to "Providers"
4. Click "Add Provider"
5. Fill in the details:
   - **Name**: e.g., "anthropic"
   - **Type**: Select from Anthropic, OpenAI, or Ollama
   - **API Key**: Your provider's API key
   - **Model**: e.g., "claude-3-sonnet-20240229"
   - **Default**: Check to make this the default provider

### 2. Start Your First Chat

1. In the main dashboard, click in the chat input at the bottom
2. Type a message like: "Hello, can you help me create a simple component?"
3. Press Enter to send

The AI will respond and you can continue the conversation.

### 3. Explore the Workspace

1. Click the Dashboard icon in the top toolbar to enter workspace mode
2. The workspace allows you to open multiple apps and views in tabs
3. Click the "Expand/Collapse" button to show or hide the chat sidebar

### 4. Create a Component

1. Open the DSPy panel by clicking the DSPy button in the chat panel
2. Click "Create Component"
3. Fill in the component details:
   - **Name**: e.g., "MyComponent"
   - **Description**: What the component does
   - **DSPy Module**: Select a module type (Reasoning, Code, QA, etc.)
4. Click "Create"

The component will be validated and added to your component registry.

### 5. Run an Agent

1. Open the Agent Runs panel
2. Click the "+" button to start a new run
3. Fill in:
   - **Goal**: What you want the agent to accomplish
   - **Autonomy Mode**: Choose from:
     - **Observe**: Agent only watches, doesn't act
     - **Suggest**: Agent suggests actions, requires approval
     - **Write Approval**: Agent can write files, requires approval
     - **Test Approval**: Agent can write and test, requires approval
     - **Autonomous**: Agent acts without approval (use with caution!)
   - **Context**: Additional context for the agent
4. Click "Start Run"

Watch the agent execute steps in the timeline. You can cancel at any time.

## Core Concepts

### Components

Components are reusable DSPy modules that perform specific tasks. They can be:
- **Reasoning**: Chain-of-thought reasoning
- **Code**: Code generation and analysis
- **QA**: Question answering
- **Summarize**: Text summarization

### Pipelines

Pipelines chain together components and tools to accomplish complex tasks. You can:
- Add component steps
- Add tool steps (terminal, filesystem, browser, database)
- Configure parameters for each step
- Run pipelines end-to-end

### Agent Runs

Agent runs are autonomous executions that:
- Plan a series of steps to achieve a goal
- Execute tools and components
- Record a timeline of all actions
- Can be paused, resumed, or cancelled

### Workspace

The workspace is a tabbed interface for:
- Opening multiple generated apps
- Viewing different React components
- Browsing documentation
- Running multiple tasks simultaneously

### Autonomy Modes

Autonomy modes control how much freedom the agent has:
- **Observe**: Agent only analyzes, doesn't make changes
- **Suggest**: Agent suggests actions, you approve each one
- **Write Approval**: Agent can write files, you approve writes
- **Test Approval**: Agent can write and test, you approve both
- **Autonomous**: Agent acts without approval (risky!)

## Common Workflows

### Creating a Full-Stack App

1. **Generate from Spec**
   - Open App Manifests panel
   - Click "Generate from Spec"
   - Fill in app details (name, backend type, views, etc.)
   - Click "Generate"

2. **Review Generated Code**
   - The app will be in "draft" status
   - Review the backend code and React views
   - Make any necessary adjustments

3. **Validate and Test**
   - Run smoke tests on the component
   - Validate React views
   - Test the app in the workspace

4. **Promote to Active**
   - Once satisfied, promote the app to "active" status
   - The app is now available for use

### Debugging an Agent Run

1. **View the Timeline**
   - Open the Agent Runs panel
   - Click on a run to expand its timeline
   - Review each step and its output

2. **Open Full Timeline**
   - Click the timeline icon for a detailed view
   - See step types, durations, and errors
   - Review metadata for each step

3. **Inspect Tool Traces**
   - Open the Tools panel
   - View recent tool executions
   - Check for errors or unexpected behavior

### Managing Components

1. **List Components**
   - Open the View Registry (list icon in toolbar)
   - Browse by category (Apps, Views, Components, Pipelines)

2. **Validate a Component**
   - Select a component
   - Click "Validate" to check syntax and imports
   - Review validation results

3. **Run Smoke Tests**
   - Click "Smoke Test" to run basic tests
   - Review test results and fix any issues

4. **Clone a Component**
   - Select a component
   - Click "Clone" to create a copy
   - Modify the copy as needed

## Keyboard Shortcuts

- **Cmd/Ctrl + K**: Open command palette
- **Cmd/Ctrl + R**: Reload the page
- **Esc**: Close panels and dialogs
- **Tab**: Navigate between fields

## Tips and Best Practices

### Security

- **Never use "Autonomous" mode with untrusted code**
- Always review agent actions before approving
- Keep your API keys secure (use environment variables)
- Regularly review tool execution logs

### Performance

- Use "Observe" or "Suggest" modes for faster iteration
- Cancel long-running agent runs if they're not progressing
- Monitor resource usage in the Monitoring Dashboard
- Clean up old agent runs periodically

### Development

- Start with simple components before building complex pipelines
- Use the workspace to test multiple components simultaneously
- Leverage the command palette for quick navigation
- Save frequently used prompts as components

## Troubleshooting

### Backend Won't Start

**Problem**: Backend fails to start with port error

**Solution**:
```bash
# Check if port 8000 is in use
lsof -i :8000

# Kill the process or change port in .env
```

### Agent Run Stuck

**Problem**: Agent run shows "running" but isn't progressing

**Solution**:
1. Check the agent logs in `.harness/logs/`
2. Cancel the run if needed
3. Review the timeline for the last successful step

### Component Validation Fails

**Problem**: Component validation shows errors

**Solution**:
1. Review the validation errors
2. Fix syntax errors in the component code
3. Check that all imports are available
4. Re-run validation

### Frontend Won't Load

**Problem**: Dashboard shows blank or error page

**Solution**:
1. Check that backend is running: `curl http://localhost:8000/health`
2. Check browser console for errors
3. Clear browser cache and reload
4. Restart frontend: `cd react && npm run dev`

## Next Steps

- Read the [Operator Runbook](OPERATOR_RUNBOOK.md) for production deployment
- Explore the [API Reference](API_REFERENCE.md) for programmatic access
- Check the [Architecture Documentation](ARCHITECTURE.md) for deep technical details
- Join the community forum for support and discussions

## Getting Help

- **Documentation**: Check the `docs/` directory for detailed guides
- **Issues**: Report bugs on GitHub Issues
- **Community**: Join our Discord/Slack for community support
- **Email**: support@vloop-harness.com for enterprise support

## Resources

- [GitHub Repository](https://github.com/your-org/Vloop-harness)
- [Documentation](https://docs.vloop-harness.com)
- [API Reference](https://api.vloop-harness.com)
- [Blog](https://blog.vloop-harness.com)

Happy building with VLoop Harness! 🚀
