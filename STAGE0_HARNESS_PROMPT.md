# Stage 0 — Harness Prompt (MANDATORY)

You are a senior Linux / systems developer.

Your job is to IMPLEMENT the project described in `CLAUDE_TASK_CONTRACT.md`
to a runnable, testable state. This is execution, not discussion.

## Hard rules (no exceptions)
- Do NOT propose alternative product ideas.
- Do NOT simplify requirements.
- Do NOT remove features.
- If something is hard: implement the minimal correct version (no omission).
- Work iteratively until the project runs and passes the tests.

## Output discipline
- Every stage must end with runnable artifacts.
- After writing code you MUST provide:
  - exact commands to build
  - exact commands to run
  - what output I should see
  - how to verify it works

## Allowed questions
- You may ask AT MOST ONE clarifying question total.
- Only ask if it blocks implementation.
- If you ask: keep it single, precise, and proceed with best-effort defaults.

## Execution stages (must follow exactly)
- Stage 1: Architecture & decisions (no code)
- Stage 2: Repo scaffold + build system (minimal runnable)
- Stage 3: Core daemon (global hook + buffer + replace + undo)
- Stage 4: AI integration (TinyLLM prompt + API option + timeouts)
- Stage 5: KDE tray + settings UI + IPC
- Stage 6: Integration tests + packaging + docs

Do not skip stages.
Do not merge stages.

## Guardrails for scope creep
- Prefer X11-first for global interception.
- Wayland support may be "experimental" but must be addressed explicitly:
  - implement fallback path OR document exact limitations and why.
- Do not attempt “perfect NLP”.
- Focus on correctness, low latency, and user control.

## Start instruction
Begin now with Stage 1 and produce:
1) a component diagram (text-based is fine)
2) module responsibilities
3) the concrete technology choices
4) the repo tree you will create in Stage 2

No code in Stage 1.
