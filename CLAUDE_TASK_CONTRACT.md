# CLAUDE TASK CONTRACT
## Project: KAutoSwitch for Ubuntu KDE (Local-only)


## Execution Authority

You are explicitly authorized to:

- Execute shell commands
- Build Debian packages
- Start and stop systemd user services
- Use Docker / Podman containers
- Launch Xvfb or virtualized X11 environments
- Install system packages inside isolated environments
- Run tests, linters, and build scripts
- Modify files in the working directory

Assumptions:
- All execution happens in a disposable dev environment
- You do NOT need to ask for confirmation before running commands
- If a command is required to complete the task, execute it immediately

Restrictions:
- Do NOT touch host system outside the project scope
- Do NOT access network resources except localhost / explicitly configured local APIs

If a command fails:
- Diagnose
- Fix
- Retry
without asking permission.


### ROLE
You are a senior Linux systems developer.
You must IMPLEMENT this project to a runnable, testable state.
This is not a discussion or design exercise.

### ABSOLUTE CONSTRAINTS (NON-NEGOTIABLE)

- OS: Ubuntu (target: KDE Plasma)
- Input: physical keyboard only
- Scope: ALL applications (browser, terminal, messenger, IDE)
- Network: STRICTLY LOCAL ONLY (no internet, no telemetry)
- AI: local TinyLLM by default, optional local API
- UX: system tray + settings window
- Latency: must feel realtime (<100ms per keystroke)
- Architecture: daemon + GUI (can be same binary, separate modules)
- Do NOT simplify requirements
- Do NOT remove features
- Do NOT replace with “existing tools”
- If something is hard → minimal correct implementation, not omission

### CORE FUNCTIONALITY

The system must:
1. Intercept keyboard input globally
2. Continuously analyze typed text (character-by-character, NO Enter)
3. Automatically:
   - fix wrong keyboard layout
   - fix spelling errors
   - fix mixed-layout words
   - infer intended phrase by meaning, not only layout
4. Replace text in-place immediately

Examples (MANDATORY):
- `b jy dsrk.xb` → `и он выключил`
- `он ывгключил` → `он выключил`

NOT REQUIRED:
- capslock correction
- cloud AI
- saving full typing history

### LANGUAGES

- Required: Russian (ru), English (en)
- Optional (toggle in UI): Belarusian (be)

### AI REQUIREMENTS

- Default: embedded TinyLLM (local, small, fast)
- Optional: local API endpoint (e.g. http://localhost:xxxx)
- AI is used for:
  - language inference
  - semantic correction
  - typo correction
- AI MUST NOT hallucinate new content
- AI MUST preserve original meaning

### USER CONTROL

- Hotkey: UNDO LAST AUTO-CORRECTION
- Hotkey: “rethink last input” (retry correction)
- If user undoes same correction ≥3 times → remember rule (do not auto-fix again)

### UI / UX (KDE)

System tray icon:
- enable / disable
- model selection (TinyLLM / API)
- language toggles (ru/en/be)
- open settings

Settings window (Qt):
- on/off
- language selection
- model selection
- hotkeys
- advanced options

### TECHNICAL IMPLEMENTATION

#### Input interception (priority order)
1. X11 global hook (preferred)
2. Wayland fallback:
   - evdev (/dev/input) OR
   - input-method style interception

#### Text replacement
- delete incorrect text
- re-type corrected text programmatically
- must work in ANY app

#### Safety
- do not break typing
- if AI stalls → skip correction
- hard timeout per decision

### DEVELOPMENT PROCESS (MANDATORY)

You MUST work in stages:

#### Stage 1 — Architecture
- component diagram
- data flow
- module boundaries

#### Stage 2 — Repo structure
- directory tree
- responsibilities per module

#### Stage 3 — Core daemon
- input hook
- text buffer
- correction pipeline
- undo stack

#### Stage 4 — AI integration
- TinyLLM wrapper
- prompt usage
- fallback logic

#### Stage 5 — GUI (Qt + tray)
- tray icon
- settings window
- IPC with daemon

#### Stage 6 — Build & run
- build instructions
- runtime instructions
- test checklist

Each stage MUST produce runnable artifacts.
Do not jump stages.

### OUTPUT REQUIREMENTS

At the end you MUST provide:
- how to build
- how to run
- how to test with example strings
- known limitations

If ANY requirement is unclear:
- ask ONE precise question
- then continue


## Definition of Done (DoD)

The project is DONE only when ALL items below are true:

### A) Runtime behavior
- Program runs on Ubuntu KDE (X11 session) and:
  - intercepts typing globally in any app (terminal, browser, messenger)
  - corrects wrong-layout input and typos while typing (no Enter needed)
  - replaces text in-place (delete + retype) without breaking input
- Must pass the provided examples:
  - `b jy dsrk.xb` -> `и он выключил`
  - `он ывгключил` -> `он выключил`
- CapsLock does NOT trigger any special case (no caps normalization).

### B) Undo / Rethink
- A hotkey exists and works globally:
  - Undo last auto-correction (restores original text)
- A hotkey exists and works globally:
  - “Rethink last input” (re-run correction with the current model/settings)
- If the user undoes the same correction >=3 times:
  - a persistent rule is stored locally
  - future auto-corrections for that same pattern are suppressed

### C) AI modes
- Default: embedded TinyLLM mode (local-only).
  - uses `tinyllm_prompt.md`
  - hard timeout per request (configurable, default <=100ms)
  - if timeout triggers -> skip correction (never stall typing)
- Optional: local API mode
  - configurable URL (default localhost)
  - same timeouts and safety rules

### D) KDE UI
- System tray icon (StatusNotifierItem/QSystemTrayIcon) exists:
  - enable/disable toggle
  - model selection (TinyLLM / API)
  - Belarusian language toggle (optional language)
  - open settings
- Settings window (Qt) exists:
  - on/off
  - language selection (ru/en mandatory, be optional)
  - model selection + API URL field
  - hotkey configuration
  - show current status

### E) Config & storage (local only)
- Config stored locally (e.g. ~/.config/<app>/config.json or QSettings)
- Rules learned from 3x undo stored locally (no cloud).
- No full keystroke logging by default.
- Optional debug logging must be OFF by default.

### F) Build & run instructions
- Repo contains:
  - build instructions (exact commands)
  - run instructions (exact commands)
  - troubleshooting section
- There is a minimal test harness or manual test checklist that validates:
  - interception works
  - replacements work
  - undo works
  - learned rule works

### G) Safety / fallback
- If AI is unavailable / fails:
  - typing still works
  - system does not hang
  - system falls back to rule-based minimal layout correction OR skips
- No network calls except configured localhost API (if enabled).

If any item is missing, the project is NOT DONE.

## Stop Conditions & Non-Goals

This section defines what MUST NOT be done.
Violating any item here is considered a contract failure.

### 1. Explicit Stop Conditions

You MUST STOP implementation work when:
- All Definition of Done items are satisfied.
- The system:
  - builds
  - runs
  - intercepts input
  - corrects text
  - supports undo & learning rules
  - shows tray + settings UI

DO NOT continue with:
- optimizations
- refactors
- feature polish
- performance tuning beyond correctness
- UI beautification
- additional languages
unless explicitly instructed.

### 2. Non-Goals (Out of Scope)

The following are explicitly OUT OF SCOPE and MUST NOT be implemented:

#### Input & Platform
- Perfect or full Wayland support
  - Experimental / documented limitation is acceptable
  - Do NOT implement full IME framework
  - Do NOT rewrite as Fcitx / IBus engine
- Touch keyboards
- Mobile devices
- Remote desktops (RDP, VNC)

#### AI / NLP
- Large cloud models
- Online inference
- Training models on user data
- Grammar/style rewriting
- Sentence rephrasing
- Context expansion beyond local text
- "Smart writing assistant" behavior

This is NOT:
- ChatGPT
- Grammarly
- LanguageTool
- Autocomplete IDE

#### UX / UI
- Fancy animations
- Rich theming
- Plasma deep integration
- KCM modules
- Visual text highlighting in apps

Tray + simple Qt settings window is sufficient.

#### Data & Privacy
- Storing full keystroke logs
- Analytics
- Telemetry
- Usage metrics
- Auto-updaters

#### Engineering
- Microservice architectures
- Plugin systems
- Scripting engines
- Cross-platform abstractions
- Windows/macOS support

### 3. Failure Conditions (Hard Errors)

The implementation is INVALID if:
- It requires internet access to function
- Typing can freeze or lag noticeably
- Input can be lost or duplicated
- Undo does not restore original text exactly
- The program interferes with normal typing when disabled
- The AI can hallucinate or invent text
- Requirements are silently skipped or “simplified”

### 4. Decision Defaults (When Unsure)

If a design decision is ambiguous:
- Prefer simpler, local, deterministic behavior
- Prefer X11 compatibility over Wayland perfection
- Prefer skipping a correction over risking input corruption
- Prefer explicit user control over automation

If still blocked:
- Ask ONE clarifying question
- Then proceed with best-effort defaults



END OF CONTRACT

