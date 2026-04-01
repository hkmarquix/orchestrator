# How to Use the RFC Spec Reasoning Engine

This repo has two phases:

1. Produce an approved spec
2. Implement the spec until team lead approval

## Prerequisites

- Python 3.9+
- A compatible LLM CLI (`codex` or any tool that accepts a prompt and writes output)

---

## Step 1 — Describe your problem

Edit `rfc_input.md`. Fill in every section as specifically as you can.

```markdown
## [RFC Request]

**Title**: Add rate limiting to the public API
**Author**: Jane Smith
**Date**: 2026-03-30
**Target system / component**: api-gateway

## [Problem Description]

The public API has no rate limiting. Three incidents in Q1 2026 resulted in
full service outages caused by a single abusive client consuming 100% of
capacity. Affected: all API consumers. Cost: ~4h downtime per incident.

## [Known Constraints]

- Must not add latency above 5ms at p99 for normal traffic
- Must work across all three API gateway instances (stateless enforcement not viable)
- Redis is already in the stack

## [Desired Outcomes]

- No single client can exceed 1000 req/min
- Legitimate traffic sees no degradation
- Blocked requests receive HTTP 429 with Retry-After header

## [Out of Scope (if known)]

- Per-endpoint rate limits (flat per-client limit only for this RFC)
- Billing-based quota tiers
```

**Tips for better output:**
- Include real numbers wherever you have them (incident counts, latency budgets, traffic volumes)
- List constraints explicitly — the generator cannot invent them
- If you already know what's out of scope, say so — it prevents the critic flagging it as a gap

---

## Step 2 — Configure your LLM

```bash
# Option A — Codex
export LLM_COMMAND='codex'
export CODEX_MODEL='gpt-5.4'          # optional
export CODEX_SANDBOX='workspace-write'
export CODEX_APPROVAL='never'

# Option B — Any other CLI
# Your CLI must accept these two placeholders:
export LLM_COMMAND='your_cli --prompt-file {prompt_file} --output-file {output_file}'
```

---

## Step 3 — Choose a mode

### With Judge (recommended for most cases)

```bash
python3 orchestrator.py
```

Loop: `Generator → Critic → Judge → Generator (fix) → ...`

The Judge filters out overcritical feedback. The generator only fixes what the Judge approves. Good for cross-team RFCs or when you want a balanced result.

### Without Judge (stricter, simpler)

```bash
python3 orchestrator.py --no-judge
```

Loop: `Generator → Critic → Generator (fix) → ...`

The Critic is the final authority. Every issue it raises must be fixed. Use this for smaller features or when you want maximum rigor.

### Custom number of rounds

```bash
python3 orchestrator.py --rounds 5
```

Default is 3. Increase if your RFC is complex and you want more refinement. Each round calls the LLM three times (with judge) or two times (without judge).

---

## Step 4 — Read the output

All output files are written in the same directory.

| File | Written by | What to read |
|------|-----------|--------------|
| `rfc_spec.md` | Generator | Your final RFC — this is the deliverable |
| `rfc_review.md` | Critic | Issues found in each round |
| `rfc_judge.md` | Judge | Verdicts per issue + fix instructions |

**The main deliverable is `rfc_spec.md`.**

After the run, check the `[Revision Status]` section at the top of `rfc_spec.md`:

```markdown
## [Revision Status]

- Mode: REVISION
- Based on Judge: YES
- Issues Addressed: 4 / 5
- Revision Round: 2
```

---

## Step 5 — Interpret the result

### Critic approved

```
Done: critic approved
Output: rfc_spec.md
```

The spec passed all audit checks. Ready to share.

### Judge soft-accepted

```
Done: judge soft-accepted
Output: rfc_spec.md
```

Only minor issues remain. The spec is usable. Read `rfc_judge.md` for the caveats.

### Judge hard-rejected (exit code 1)

```
Done: judge hard-rejected — spec needs major rework
Output: rfc_spec.md
```

A fundamental structural problem was found. Read `rfc_judge.md` → `[Final Decision]` section for the reason. Update `rfc_input.md` with more detail, then re-run.

### Max rounds reached

```
Done: reached max rounds (3)
Output: rfc_spec.md
```

The loop hit the limit. Read `rfc_review.md` to see what issues the critic still has. Either increase `--rounds`, fix `rfc_input.md` with more context, or accept the current `rfc_spec.md` as-is.

---

## Step 6 — Run the implementation loop

Once `rfc_spec.md` is approved, start coding:

```bash
python3 implementation_orchestrator.py
python3 implementation_orchestrator.py --rounds 5
```

Loop:

```text
Senior Dev → Team Lead Review → Senior Dev (fix) → ... → Handoff
```

Behavior:
- The senior dev edits the codebase to match `rfc_spec.md`
- The senior dev writes `implementation_report.md`
- The team lead reviews the actual code and writes `code_review.md`
- The loop continues until the team lead writes `APPROVED`
- After approval, the senior dev writes `handoff_report.md`

Implementation artifacts:

| File | Written by | What it means |
|------|-----------|---------------|
| `implementation_report.md` | Senior Dev | What changed, what was verified, and what risks remain |
| `code_review.md` | Team Lead | Review findings, verification status, and approval decision |
| `handoff_report.md` | Senior Dev | Final handoff after approval |

Implementation stopping conditions:

| Condition | Exit code |
|-----------|-----------|
| Team lead issues `APPROVED` | 0 |
| Max rounds reached without approval | 1 |

---

## Re-running

Each run clears `rfc_spec.md`, `rfc_review.md`, and `rfc_judge.md` before starting. Your input `rfc_input.md` is never modified.

To re-run from scratch:

```bash
python3 orchestrator.py
```

To continue with a different mode on the same input:

```bash
python3 orchestrator.py --no-judge --rounds 2
```

---

## Stopping conditions reference

| Condition | Mode | Exit code |
|-----------|------|-----------|
| Critic issues `APPROVED` | Both | 0 |
| Judge issues `SOFT_ACCEPT` | With judge | 0 |
| Judge issues `HARD_REJECT` | With judge | 1 |
| Max rounds reached | Both | 0 |

---

## Troubleshooting

**`LLM_COMMAND is not set and codex was not found on PATH`**
Install `codex` or set `LLM_COMMAND`. See Step 2.

**`Missing required file: rfc_input.md`**
`rfc_input.md` must exist and have content before running.

**Critic never approves after 3 rounds**
Usually means `rfc_input.md` is too vague. Add concrete constraints, numbers, and known non-goals, then re-run. Alternatively use `--rounds 5` to give the loop more iterations.

**Judge keeps issuing `HARD_REJECT`**
The problem description has a structural gap the generator cannot fill. Read `rfc_judge.md` → `[Final Decision]` for the specific reason, update `rfc_input.md`, and re-run.

**Output looks right but `rfc_spec.md` is empty**
Your LLM CLI is not writing to the output file or stdout. Test your `LLM_COMMAND` manually with a simple prompt first.

**`--no-judge` but critic is too aggressive**
The critic has no calibration without the judge. If it is flagging reasonable things as errors, switch to the default mode (with judge) — the judge's job is exactly to filter that.
