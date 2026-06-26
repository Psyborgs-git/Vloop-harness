# React Frontend Specification

The React frontend is the user-facing application shell for VLoop. It is served by the Python Control Plane and communicates only with CP HTTP/WebSocket APIs.

---

## 1. Project Structure

```
src/
├── index.html                       # Entry HTML
├── package.json                     # Dependencies & scripts
├── tsconfig.json                    # TypeScript config
├── vite.config.ts                   # Vite bundler config
└── src/
    ├── main.tsx                     # React entry point
    ├── App.tsx                      # Root component (shell + view router)
    ├── hooks/
    │   └── useAppData.ts            # Centralized state, polling, mutations
    ├── components/
    │   ├── ui.tsx                   # Shared UI primitives (Panel, Badge, etc.)
    │   ├── Sidebar.tsx              # Navigation sidebar with theme toggle & collapse
    │   └── Toolbar.tsx              # Top toolbar with status & refresh
    ├── views/
    │   ├── DashboardView.tsx        # Overview: health, metrics, next steps
    │   ├── ChatView.tsx             # Conversational agent chat
    │   ├── SettingsView.tsx         # Database & vector store configuration
    │   ├── SetupView.tsx            # Dependency check dashboard
    │   ├── SystemView.tsx           # System observability (health, session, events)
    │   ├── UsageView.tsx            # Token usage analytics & trace drill-down
    │   ├── WorkloadsView.tsx        # Docker container workload management
    │   ├── agents/                  # Agent management (split from monolithic view)
    │   │   ├── AgentsView.tsx       # Agent orchestrator (list + form)
    │   │   ├── AgentList.tsx        # Agent selection sidebar
    │   │   ├── AgentForm.tsx        # Agent create/edit form
    │   │   ├── AgentFormTypes.ts    # Type definitions for agent forms
    │   │   └── AgentFormHelpers.ts  # Validation, serialization, conversion
    │   ├── providers/               # Provider management (split from monolithic view)
    │   │   ├── ProvidersView.tsx    # Provider orchestrator (list + form)
    │   │   ├── ProviderList.tsx     # Provider selection sidebar
    │   │   ├── ProviderForm.tsx     # Provider create/edit form
    │   │   ├── ProviderFormTypes.ts # Type definitions for provider forms
    │   │   └── ProviderFormHelpers.ts # Validation, serialization, conversion
    │   └── playground/              # Agent playground (split from monolithic view)
    │       ├── PlaygroundView.tsx   # Playground orchestrator
    │       ├── InputForm.tsx        # Dynamic input fields
    │       ├── OverridesPanel.tsx   # Provider/model/temperature overrides
    │       ├── InvocationDetails.tsx # Output/results display
    │       └── RecentRuns.tsx       # Recent invocations list
    ├── lib/
    │   ├── api.ts                   # Barrel re-export file (backward compat)
    │   ├── types.ts                 # All TypeScript interfaces/types
    │   ├── api-client.ts            # fetch wrappers, error handling, parsing
    │   ├── helpers.ts               # Sort, filter, identifier utilities
    │   ├── normalizers.ts           # Response normalizer functions
    │   └── endpoints/
    │       ├── agent.ts             # Agent CRUD, templates, invocations
    │       ├── provider.ts          # Provider CRUD, catalog, testing
    │       ├── system.ts            # Bootstrap, system snapshot, shutdown, settings
    │       └── workloads.ts         # Workload CRUD operations
    └── styles/
        ├── main.css                 # Entry point (imports all modules)
        ├── tokens.css               # Design tokens & light/dark theme variables
        ├── reset.css                # Reset & base styles
        ├── layout.css               # App shell, sidebar (with collapsed mini-mode), toolbar, responsive
        ├── panels.css               # Panels, cards, metrics, timeline, code blocks
        ├── buttons.css              # Buttons, badges, notices
        ├── forms.css                # Form fields, inputs, segmented controls
        ├── chat.css                 # Chat view specific styles
        ├── pages.css                # Page layout helpers
        └── accessibility.css        # Reduced motion, focus, screen reader
```

## 2. Architecture

### Data Flow

```
App.tsx
  └── useAppData() hook  ←  all state management
        ├── getBootstrap()     →  providers, agents, invocations, templates
        ├── getSystemSnapshot() →  health, session, window, events, dependencies
        ├── Polling (4s system, 12s bootstrap)
        └── Mutation callbacks  (save/delete/test)
          ↓
    Sidebar + Toolbar + ActiveView
```

### Component Tree

```
App
├── Sidebar (collapsible with icon mini-mode, theme toggle, nav, quit)
├── Toolbar (status badge, refresh button)
└── ActiveView (switches on view)
    ├── DashboardView
    ├── ProvidersView → ProviderList + ProviderForm
    ├── AgentsView → AgentList + AgentForm
    ├── ChatView
    ├── PlaygroundView → InputForm + OverridesPanel + InvocationDetails + RecentRuns
    ├── UsageView
    ├── SystemView
    ├── SetupView
    ├── SettingsView
    └── WorkloadsView
```

### API Client Organization

The `lib/api.ts` file has been split into focused sub-modules:

| Module | Contents |
|---|---|
| `lib/types.ts` | All TypeScript interfaces (ProviderConfig, AgentConfig, InvocationRecord, etc.) |
| `lib/api-client.ts` | HTTP fetch wrappers (`requestJson`, `requestWithFallback`), error handling, body parsing |
| `lib/normalizers.ts` | Response normalization functions for all entity types |
| `lib/helpers.ts` | Sort functions, invocation status checks, identity utilities |
| `lib/endpoints/provider.ts` | Provider CRUD API calls and catalog fetching |
| `lib/endpoints/agent.ts` | Agent CRUD, templates, chat, and invocation API calls |
| `lib/endpoints/system.ts` | Bootstrap, system snapshot, shutdown, and settings API calls |
| `lib/endpoints/workloads.ts` | Workload CRUD API calls |
| `lib/api.ts` | Barrel re-export for backward compatibility |

## 3. Theme System

The app supports light and dark modes via CSS custom properties:

- **Light**: default, warm neutral tones using oklch color space
- **Dark**: activated by OS preference (`prefers-color-scheme`) **or** explicit toggle
- **Auto mode**: respects OS preference; user can override via sidebar toggle
- Theme preference is persisted in `localStorage` under `vloop-theme`
- All themed elements transition smoothly (300ms ease) between modes
- Dark mode includes custom scrollbar styling

### Toggle Controls

The sidebar footer includes:
- Light theme button (☀)
- Dark theme button (☾)
- Current mode indicator (Light/Dark/Auto)

## 4. Sidebar

The sidebar is **collapsible** with a mini icon-only mode:

- **Expanded**: Shows brand block, full navigation labels with descriptions, status badges, theme toggle, and quit button
- **Collapsed (mini-mode)**: Shows icon-only navigation (emoji icons), compact count badges, centered theme toggle, and hidden quit button
- Navigation items display counts (provider count, agent count, invocation count) as numbered badges
- Expand/collapse with a floating toggle button (←/→ arrow)
- State persisted in `localStorage` (`vloop-sidebar-collapsed`)
- Width transitions smoothly (280ms cubic-bezier) between 17rem expanded and 3.5rem collapsed

## 5. Views Refactoring

The three largest view files were broken into sub-components for better maintainability:

### Agents View (was ~1080 lines → 5 files)
- `AgentsView.tsx` — orchestrator, manages agent selection and form lifecycle
- `AgentList.tsx` — sidebar list of agents with counts
- `AgentForm.tsx` — create/edit form with template application
- `AgentFormTypes.ts` — `AgentFieldState`, `AgentFormState`, `AgentValidationState` interfaces
- `AgentFormHelpers.ts` — validation, serialization, slugification utilities

### Providers View (was ~713 lines → 5 files)
- `ProvidersView.tsx` — orchestrator, manages provider selection and form lifecycle
- `ProviderList.tsx` — sidebar list of providers with status badges
- `ProviderForm.tsx` — create/edit form with secret mode, API base, model configuration
- `ProviderFormTypes.ts` — `ProviderFormState`, `ProviderValidation` interfaces
- `ProviderFormHelpers.ts` — validation, serialization, form conversion utilities

### Playground View (was ~700 lines → 5 files)
- `PlaygroundView.tsx` — orchestrator, manages invocation lifecycle and run selection
- `InputForm.tsx` — dynamic input fields based on agent's input schema
- `OverridesPanel.tsx` — provider, model, temperature, max tokens overrides
- `InvocationDetails.tsx` — output text, JSON results, reasoning, error display
- `RecentRuns.tsx` — invocation history list with status badges