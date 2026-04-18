# Phase 0 — The Foundation

## What this phase is

Everything that v1 assumes you already know.

When v1 arrives and Claude analyzes a log in one API call, you will understand exactly what just happened and why it matters — because you will have already done it the hard way. You will have written the bash version. You will have felt the brittleness. You will know what tokens and context windows are. You will understand why structured output is hard without tooling.

Phase 0 is not optional background reading. It is the ground everything else is built on.

---

## What you will know by the end

- Navigate any Linux system without hesitation
- Write bash scripts that automate real tasks
- Use git properly — not just the commands, but the mental model
- Understand HTTP, REST, and curl at a level where you can debug any API call
- Set up a Python project correctly from scratch
- Build a FastAPI endpoint and understand every line
- Know what a token is, what a context window is, what a system prompt does — before you touch any framework

---

## The versions

| Version | Topic | What you build |
|---------|-------|----------------|
| v0.1 | Linux Essentials | `sysinfo.sh` — system report script |
| v0.2 | Bash Scripting | `log_analyzer.sh` — brittle pattern matcher that makes v1 land harder |
| v0.3 | Git & GitHub | This repo, committed properly with real history |
| v0.4 | Networking & HTTP | curl real APIs, understand the full request/response cycle |
| v0.5 | Python for This Project | venv, Pydantic models, .env, the exact patterns used throughout |
| v0.6 | Your First API (No AI) | Mock AOIS endpoint — regex-based analysis, no Claude |
| v0.7 | How LLMs Work | Raw Claude API call before any framework |

---

## The narrative arc

v0.2 ends with a bash log analyzer that handles 3 patterns and misses everything else.
v0.6 ends with a Python API that does regex matching — more structured, still brittle.
v0.7 ends with a raw Claude call returning unstructured text.

Then v1 arrives. Structured output. Four routing tiers. Prompt caching. One call that handles every log you've ever seen.

That sequence is why Phase 0 exists.
