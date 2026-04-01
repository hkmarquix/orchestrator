# RFC Spec Reasoning Engine

A multi-agent system that first produces a better RFC / spec ticket, then drives implementation until code review approval and handoff.

Inspired by the Eight Fortune Reasoning Engine — same loop, applied to software engineering.

---

## What It Does

Instead of writing an RFC once and hoping it's good, this repo supports two delivery phases:

1. Spec refinement
2. Implementation delivery

### Phase 1: Spec refinement

This phase runs a self-correcting loop:

```
Generator → Critic → [Judge] → Generator (fix) → repeat
```

1. **Generator** — writes a structured RFC from your problem description
2. **Critic** — audits the RFC for vague requirements, missing reasoning, untestable criteria, scope gaps, and more
3. **Judge** *(optional)* — arbitrates between the critic and generator, filters overcritical feedback, issues precise fix instructions
4. Repeat until the critic approves, the judge accepts, or max rounds is reached

### Phase 2: Implementation delivery

After the spec is approved, a second loop drives coding work:

```
Senior Dev → Team Lead Review → Senior Dev (fix) → repeat → Handoff
```

1. **Senior Dev** — implements the approved spec directly in the codebase and writes `implementation_report.md`
2. **Team Lead** — reviews the actual code, verifies behavior against the spec, and writes `code_review.md`
3. Repeat until the team lead issues `APPROVED`
4. **Senior Dev** writes `handoff_report.md` after approval

---

## Core Idea

> A "code review system" for your spec — before a single line of code is written

The system enforces:

- No vague language (`"fast"`, `"scalable"`, `"simple"` without measurable conditions)
- Full reasoning chains: `[Requirement] → [Constraint] → [Decision] → [Trade-off]`
- Testable success criteria: `Given / When / Then`
- Explicit scope and non-goals
- Alternatives considered for every major decision
- Named risks and unknowns

---

## Project Structure

```
.
├── orchestrator.py                 # Spec refinement loop
├── implementation_orchestrator.py  # Coding / review / handoff loop
├── rfc_input.md                    # Input for RFC generation
├── rfc_spec.md                     # Approved spec
├── rfc_review.md                   # Spec critic output
├── rfc_judge.md                    # Spec judge output
├── implementation_report.md        # Senior dev status report
├── code_review.md                  # Team lead review and approval
├── handoff_report.md               # Final handoff after approval
└── prompts/
    ├── generator.txt
    ├── critic.txt
    ├── judge.txt
    ├── senior_dev.txt
    ├── team_lead.txt
    └── handoff.txt
```

---

## Two Modes

### With Judge (default)

```
Generator → Critic → Judge → Generator (fix) → ...
```

- Judge filters overcritical feedback
- Generator only fixes what the Judge approves
- Stops on: critic APPROVED, judge SOFT_ACCEPT, judge HARD_REJECT, or max rounds

Use when: cross-team RFCs, high-stakes design decisions, or when the critic keeps blocking on minor issues.

### Without Judge (`--no-judge`)

```
Generator → Critic → Generator (fix) → ...
```

- Critic is the final authority
- Simpler, faster, stricter
- Stops on: critic APPROVED or max rounds

Use when: small features, internal tools, or when you want maximum strictness.

---

## Quick Start

```bash
# 1. Fill in your problem
edit rfc_input.md

# 2. Set your LLM
export LLM_COMMAND='codex'
export CODEX_MODEL='gpt-5.4'

# 3. Run
python3 orchestrator.py               # with judge
python3 orchestrator.py --no-judge    # without judge
python3 orchestrator.py --rounds 5    # more iterations

# 4. After the spec is approved, implement it
python3 implementation_orchestrator.py
python3 implementation_orchestrator.py --rounds 5
```

---

## Agent Roles

| Role | Responsibility | Writes to |
|------|---------------|-----------|
| Generator | Produce and revise the RFC | `rfc_spec.md` |
| Critic | Find every flaw — default stance is distrust | `rfc_review.md` |
| Judge | Arbitrate, filter noise, issue fix instructions | `rfc_judge.md` |
| Senior Dev | Implement the approved spec in code | `implementation_report.md` |
| Team Lead | Review code and verify it works against the spec | `code_review.md` |
| Senior Dev (handoff) | Write the final implementation handoff | `handoff_report.md` |

### What the Critic checks

| Issue Type | Description |
|------------|-------------|
| `VAGUE` | Unmeasured adjectives or conditionals |
| `LOGIC_GAP` | Design decision missing a reasoning link |
| `UNTESTABLE` | Success criterion not in Given/When/Then form |
| `SCOPE_GAP` | Non-goals absent or ambiguous |
| `UNDEFINED_TERM` | Term used before definition |
| `NO_ALTERNATIVES` | Major decision with no alternatives documented |
| `RISK_GAP` | No risks named on a non-trivial feature |
| `CONTRADICTION` | Two sections making incompatible claims |
| `PLAN_GAP` | Tasks not independently deliverable |
| `MISSING_OWNER` | Open questions with no owner or deadline |

---

## Stopping Conditions

| Condition | Exit code |
|-----------|-----------|
| Critic issues `APPROVED` | 0 |
| Judge issues `SOFT_ACCEPT` | 0 |
| Judge issues `HARD_REJECT` | 1 |
| Max rounds reached | 0 |

### Implementation phase

| Condition | Exit code |
|-----------|-----------|
| Team lead issues `APPROVED` | 0 |
| Max rounds reached without approval | 1 |

---

## RFC Output Structure

The final `rfc_spec.md` always contains:

- RFC Header (title, status, author, date, target system)
- Problem Statement
- Goals (measurable)
- Non-Goals (explicit)
- Background & Context
- Proposed Solution with reasoning chains
- Alternatives Considered
- Implementation Plan (phased, with dependencies)
- Success Criteria (Given/When/Then)
- Risks & Unknowns
- Open Questions

---

## Design Principles

### 1. Separation of Roles

The generator never critiques. The critic never fixes. The judge never writes content. Each agent does exactly one job.

### 2. Controlled Convergence

The generator only fixes what the Judge approved. This prevents random rewrites, overfitting to critic feedback, and infinite loops.

### 3. Minimum Diff

Each revision makes the smallest change that satisfies the approved fix instructions. Sections not flagged must not change.

### 4. Objective Exit Criteria

Unlike subjective domains, programming specs have testable correctness: does every success criterion have a Given/When/Then? Are non-goals listed? These are binary checks, which means the critic can converge.

---

## Requirements

- Python 3.9+
- A compatible LLM CLI (`codex` or any CLI accepting `{prompt_file}` / `{output_file}` placeholders)

---

## Relationship to the BaZi Version

This project applies the same reasoning loop from the Eight Fortune Reasoning Engine to software specs. The key differences:

| | BaZi | Programming |
|---|---|---|
| Target output | Fortune analysis | RFC / spec ticket |
| Judge | Always on | Optional (`--no-judge`) |
| Correctness | Subjective | Partially objective (testable criteria, scope, etc.) |
| Exit without judge | N/A | Supported |
| Critic issue types | VAGUE, LOGIC_GAP, etc. | Extended set including SCOPE_GAP, PLAN_GAP, RISK_GAP |
