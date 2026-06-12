---
name: Vloop Harness
description: A local-first AI engineering workbench for DSPy agents
colors:
  primary: "#6366f1"
  primary-dark: "#4f46e5"
  primary-light: "#818cf8"
  secondary: "#ec4899"
  secondary-dark: "#db2777"
  background-default: "#0f0f13"
  background-paper: "#1a1a24"
  divider: "rgba(255,255,255,0.08)"
  text-primary: "#e2e8f0"
  text-secondary: "#94a3b8"
  text-disabled: "#475569"
typography:
  display:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "clamp(2rem, 5vw, 3.5rem)"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 600
    lineHeight: 1.3
  title:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.5
    letterSpacing: "0.05em"
rounded:
  md: "8px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "8px 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-dark}"
  button-secondary:
    backgroundColor: "{colors.secondary}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "8px 16px"
  button-secondary-hover:
    backgroundColor: "{colors.secondary-dark}"
---

# Design System: Vloop Harness

## 1. Overview

**Creative North Star: "The Fluid Terminal"**

Vloop Harness is designed as a highly secure, privacy-first developer workspace that bridges the gap between deep infrastructure sandboxing and visual AI execution. Modeled after modern CLI shells and local-first IDEs, "The Fluid Terminal" prioritizes screen density, instant responsiveness, and distraction-free layouts to keep AI engineers in their flow. 

The aesthetic is characterized by high-contrast monochrome foundations accented with purposeful, vibrant signals that represent active states and pipeline execution. It explicitly rejects cluttered SaaS dashboard patterns, non-intuitive layered shadows, and unnecessary decorative glassmorphism.

**Key Characteristics:**
- **Zero-Latency Feel**: Snappy micro-interactions and transitions with standard exponential easing.
- **Strict Information Density**: Compact spacing, legible typography, and structured content boundaries.
- **Visual Gating**: Status colors are used sparingly (≤10% of any screen surface) to indicate agent execution and system safety.

## 2. Colors

The color palette centers around deep, obsidian neutral tones with sharp violet and pink highlights representing cognitive engine activity.

### Primary
- **Intelligent Indigo** (#6366f1 / oklch(65% 0.2 270)): Used for core actions, primary selections, and active pipeline transitions. Represents structural control.

### Secondary
- **Fluid Magenta** (#ec4899 / oklch(65% 0.22 340)): Used for agent status, feedback pulses, and human-in-the-loop triggers. Represents dynamic cognitive activity.

### Neutral
- **Obsidian Vault** (#0f0f13): The canonical workspace background.
- **Obsidian Paper** (#1a1a24): Surfaces, containers, and card layers.
- **Slate Text Primary** (#e2e8f0): Primary headings and body copy.
- **Slate Text Secondary** (#94a3b8): Meta text, labels, and helper copy.
- **Slate Text Disabled** (#475569): Inactive text and placeholder indicators.
- **System Divider** (rgba(255,255,255,0.08)): 1px borders dividing UI sections.

### Named Rules
**The Obsidian Restraint Rule.** The primary "Intelligent Indigo" accent should never cover more than 10% of any screen. If everything glows, nothing is important.
**The No-Faux-Glow Rule.** Do not use colored glowing shadows around cards or text. Colors are indicators of state and system health, not decorative trim.

## 3. Typography

**Display Font:** Inter (system-ui, sans-serif)
**Body Font:** Inter (system-ui, sans-serif)
**Mono Font:** monospace

**Character:** Highly uniform, clean geometric sans-serif prioritizing legibility at dense grid structures.

### Hierarchy
- **Display** (600, clamp(2rem, 5vw, 3.5rem), 1.2): Only used for massive dashboard headers or setup success overlays.
- **Headline** (600, 1.75rem, 1.3): Used for panel-level headers.
- **Title** (600, 1.25rem, 1.4): Card titles, workspace window headers.
- **Body** (400, 0.875rem, 1.5): Standard prose and description text. Max line length: 75ch.
- **Label** (500, 0.75rem, 1.5, letter-spacing: 0.05em): Uppercase or tracked meta headers, table labels, active button text.

### Named Rules
**The Monospace Equality Rule.** Use code blocks and monospace font families for all pipeline steps, sandbox states, and terminal commands to maintain an authentic local-first environment feel.

## 4. Elevation

Depth is conveyed strictly through borders and tonal changes, completely flat at rest.

### Depth Vocabulary
- **At-Rest Level**: Obsidian Vault background (#0f0f13).
- **Container Level**: Obsidian Paper containers (#1a1a24) bounded by a 1px border of System Divider (rgba(255,255,255,0.08)).
- **Interactions**: Elevated only on hover with flat white borders or a subtle slate border. No soft drop shadows or heavy blurs.

### Named Rules
**The Flat-By-Default Rule.** Surfaces are perfectly flat at rest. Shadow vocabulary is completely absent; instead, elevation is suggested strictly by a shift in container background or border contrast.

## 5. Components

### Buttons
- **Shape:** Soft rounded corners (8px radius)
- **Primary:** Intelligent Indigo background with Slate Text Primary. Padding is compact (8px 16px).
- **Secondary:** Fluid Magenta background for high-priority interactive tasks.
- **Hover / Focus:** Hovering transitions background color with an instant 0.15s ease-in-out. Focus displays a 2px offset solid outline in Intelligent Indigo.

### Cards / Containers
- **Corner Style:** Soft rounded corners (8px radius)
- **Background:** Obsidian Paper (#1a1a24)
- **Border:** 1px solid rgba(255,255,255,0.08)
- **Internal Padding:** Spaced compactly (16px)

### Inputs / Fields
- **Style:** Obsidian Vault background (#0f0f13) with a 1px System Divider border and 8px border radius.
- **Focus:** Sharp border transition to Intelligent Indigo. No glow.
- **Error / Disabled:** Error state switches border to Fluid Magenta. Disabled reduces opacity to 40%.

### Navigation
- Compact left drawer with background #13131a and a 1px right border. Selections use Intelligent Indigo background with 20% opacity.

## 6. Do's and Don'ts

### Do:
- **Do** use monospace fonts for commands, sandbox IDs, and dspy configurations.
- **Do** keep spacing compact to ensure all telemetry, sandboxes, and logs fit on a single screen without scrolling where possible.
- **Do** use Fluid Magenta strictly to represent human-in-the-loop requests and urgent sandbox actions.

### Don't:
- **Don't** use soft decorative drop shadows or glassmorphism backgrounds.
- **Don't** use multi-color gradient text or colorful card glow effects.
- **Don't** use thick left-side accent borders on callouts or cards.
- **Don't** use heavy margin spacing that dilutes screen density and forces the developer out of the terminal flow.
