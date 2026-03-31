#!/usr/bin/env python3
"""
RFC Spec Reasoning Engine
Multi-agent loop: Generator → Critic [→ Judge] → Generator (fix) → ...

Usage:
    python orchestrator.py                  # judge enabled (default)
    python orchestrator.py --no-judge       # judge disabled: critic is final authority
    python orchestrator.py --rounds 5       # override max rounds

Environment:
    LLM_COMMAND     LLM CLI to use (default: auto-detect 'codex')
    CODEX_MODEL     Model name (e.g. 'gpt-5.4')
    CODEX_SANDBOX   Sandbox mode (default: workspace-write)
    CODEX_APPROVAL  Approval mode (default: never)
    CODEX_SEARCH    Enable web search (default: 1)
"""
from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


BASE_DIR = Path(__file__).parent
PROMPTS_DIR = BASE_DIR / "prompts"

INPUT_FILE = BASE_DIR / "rfc_input.md"
SPEC_FILE = BASE_DIR / "rfc_spec.md"
REVIEW_FILE = BASE_DIR / "rfc_review.md"
JUDGE_FILE = BASE_DIR / "rfc_judge.md"

GENERATOR_PROMPT_FILE = PROMPTS_DIR / "generator.txt"
CRITIC_PROMPT_FILE = PROMPTS_DIR / "critic.txt"
JUDGE_PROMPT_FILE = PROMPTS_DIR / "judge.txt"

DEFAULT_MAX_ROUNDS = 3


@dataclass
class Decisions:
    review_decision: Optional[str] = None
    judge_final_decision: Optional[str] = None
    issues_addressed: Optional[str] = None


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def require_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return read_text(path)


def normalize_decision(value: str) -> str:
    return value.strip().upper().replace(" ", "_")


def normalize_codex_sandbox(value: str) -> str:
    normalized = value.strip().lower()
    legacy_aliases = {
        "seatbelt": "workspace-write",
        "sandbox": "workspace-write",
    }
    normalized = legacy_aliases.get(normalized, normalized or "workspace-write")
    allowed = {"read-only", "workspace-write", "danger-full-access"}
    if normalized not in allowed:
        raise RuntimeError(
            f"Unsupported CODEX_SANDBOX value: {value!r}. "
            f"Expected one of: {', '.join(sorted(allowed))}."
        )
    return normalized


def extract_review_decision(text: str) -> Optional[str]:
    patterns = [
        r"##\s*\[Decision\]\s*[:：]?\s*\n+([A-Z_]+)",
        r"##\s*\[Decision\]\s*[:：]?\s*([A-Z_]+)",
        r"\[Decision\]\s*[:：]?\s*([A-Z_]+)",
        r"Decision\s*[:：]\s*([A-Z_]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return normalize_decision(match.group(1))
    return None


def extract_judge_final_decision(text: str) -> Optional[str]:
    patterns = [
        r"##\s*\[Final Decision\]\s*[:：]?\s*\n+([A-Z_]+)",
        r"##\s*\[Final Decision\]\s*[:：]?\s*([A-Z_]+)",
        r"\[Final Decision\]\s*[:：]?\s*([A-Z_]+)",
        r"Final Decision\s*[:：]\s*([A-Z_]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return normalize_decision(match.group(1))
    return None


def extract_issues_addressed(text: str) -> Optional[str]:
    match = re.search(r"Issues Addressed\s*[:：]\s*([^\n]+)", text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


def build_prompt(
    role_prompt: str,
    *,
    input_data: str,
    spec: str,
    review: str,
    judge: str,
    use_judge: bool,
) -> str:
    judge_section = (
        f"[FILE: rfc_judge.md]\n{judge if judge else '(not used — judge disabled)'}"
        if use_judge
        else "[FILE: rfc_judge.md]\n(disabled — running without judge)"
    )

    return f"""{role_prompt}

=======================
WORKSPACE FILES
=======================

[FILE: rfc_input.md]
{input_data if input_data else "(missing)"}

[FILE: rfc_spec.md]
{spec if spec else "(missing)"}

[FILE: rfc_review.md]
{review if review else "(missing)"}

{judge_section}

=======================
TASK EXECUTION RULES
=======================

- Read the workspace files above as the current source of truth.
- Follow your role prompt exactly.
- If you are the generator, output ONLY the full content of rfc_spec.md.
- If you are the critic, output ONLY the full content of rfc_review.md.
- If you are the judge, output ONLY the full content of rfc_judge.md.
- Do not add any explanation or commentary outside the file content.
- Do NOT write to any files. Output the file content directly in your response only.
"""


def call_model(prompt: str) -> str:
    command_template = os.environ.get("LLM_COMMAND", "").strip()
    if not command_template:
        codex_path = shutil.which("codex")
        if codex_path:
            command_template = "codex"
        else:
            raise RuntimeError(
                "LLM_COMMAND is not set and `codex` was not found on PATH.\n"
                "Use either:\n"
                "  export LLM_COMMAND='codex'\n"
                "or:\n"
                "  export LLM_COMMAND='your_cli --prompt-file {prompt_file} --output-file {output_file}'"
            )

    if command_template == "codex":
        codex_model = os.environ.get("CODEX_MODEL", "").strip()
        codex_sandbox = normalize_codex_sandbox(
            os.environ.get("CODEX_SANDBOX", "workspace-write")
        )
        codex_approval = os.environ.get("CODEX_APPROVAL", "never").strip() or "never"
        codex_search_raw = os.environ.get("CODEX_SEARCH", "1").strip().lower()
        codex_search_enabled = codex_search_raw not in {"0", "false", "no", "off"}

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            output_file = tmpdir_path / "output.txt"

            command = ["codex"]

            if codex_model:
                command.extend(["--model", codex_model])

            if codex_search_enabled:
                command.append("--search")

            command.extend([
                "--ask-for-approval", codex_approval,
                "exec",
                "--skip-git-repo-check",
                "--sandbox", codex_sandbox,
                "--output-last-message", str(output_file),
                prompt,
            ])

            result = subprocess.run(command, capture_output=True, text=True, check=False)

            if result.returncode != 0:
                raise RuntimeError(
                    f"Codex command failed.\n"
                    f"Return code: {result.returncode}\n"
                    f"STDOUT:\n{result.stdout}\n"
                    f"STDERR:\n{result.stderr}"
                )

            if output_file.exists():
                output = output_file.read_text(encoding="utf-8").strip()
                if output:
                    return output

            output = result.stdout.strip()
            if output:
                return output

            raise RuntimeError("Codex command succeeded but produced no final output.")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        prompt_file = tmpdir_path / "prompt.txt"
        output_file = tmpdir_path / "output.txt"

        prompt_file.write_text(prompt, encoding="utf-8")

        command = command_template.format(
            prompt_file=str(prompt_file),
            output_file=str(output_file),
        )

        result = subprocess.run(
            shlex.split(command), capture_output=True, text=True, check=False
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"LLM command failed.\n"
                f"Return code: {result.returncode}\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}"
            )

        if output_file.exists():
            return output_file.read_text(encoding="utf-8").strip()

        stdout = result.stdout.strip()
        if stdout:
            return stdout

        raise RuntimeError(
            "LLM command succeeded but produced no output. "
            f"Either write to {output_file} or print to stdout."
        )


def run_generator(use_judge: bool) -> None:
    role_prompt = require_file(GENERATOR_PROMPT_FILE)
    prompt = build_prompt(
        role_prompt,
        input_data=require_file(INPUT_FILE),
        spec=read_text(SPEC_FILE),
        review=read_text(REVIEW_FILE),
        judge=read_text(JUDGE_FILE),
        use_judge=use_judge,
    )
    output = call_model(prompt)
    write_text(SPEC_FILE, output)


def run_critic(use_judge: bool) -> None:
    role_prompt = require_file(CRITIC_PROMPT_FILE)
    prompt = build_prompt(
        role_prompt,
        input_data=require_file(INPUT_FILE),
        spec=read_text(SPEC_FILE),
        review=read_text(REVIEW_FILE),
        judge=read_text(JUDGE_FILE),
        use_judge=use_judge,
    )
    output = call_model(prompt)
    write_text(REVIEW_FILE, output)


def run_judge(use_judge: bool) -> None:
    role_prompt = require_file(JUDGE_PROMPT_FILE)
    prompt = build_prompt(
        role_prompt,
        input_data=require_file(INPUT_FILE),
        spec=read_text(SPEC_FILE),
        review=read_text(REVIEW_FILE),
        judge=read_text(JUDGE_FILE),
        use_judge=use_judge,
    )
    output = call_model(prompt)
    write_text(JUDGE_FILE, output)


def summarize_state(round_number: int, use_judge: bool) -> Decisions:
    review_text = read_text(REVIEW_FILE)
    judge_text = read_text(JUDGE_FILE)
    spec_text = read_text(SPEC_FILE)

    decisions = Decisions(
        review_decision=extract_review_decision(review_text),
        judge_final_decision=extract_judge_final_decision(judge_text) if use_judge else None,
        issues_addressed=extract_issues_addressed(spec_text),
    )

    print(f"\n=== Round {round_number} Summary ===")
    print(f"Review decision      : {decisions.review_decision or 'UNKNOWN'}")
    if use_judge:
        print(f"Judge final decision : {decisions.judge_final_decision or 'N/A'}")
    else:
        print(f"Judge final decision : (disabled)")
    print(f"Issues addressed     : {decisions.issues_addressed or 'N/A'}")
    return decisions


def should_stop(decisions: Decisions, use_judge: bool) -> tuple[bool, str]:
    if decisions.review_decision == "APPROVED":
        return True, "critic approved"
    if use_judge:
        if decisions.judge_final_decision == "SOFT_ACCEPT":
            return True, "judge soft-accepted"
        if decisions.judge_final_decision == "HARD_REJECT":
            return True, "judge hard-rejected — spec needs major rework"
    return False, ""


def ensure_files_exist(use_judge: bool) -> None:
    required = [INPUT_FILE, GENERATOR_PROMPT_FILE, CRITIC_PROMPT_FILE]
    if use_judge:
        required.append(JUDGE_PROMPT_FILE)
    missing = [p for p in required if not p.exists()]
    if missing:
        names = "\n".join(f"  - {p}" for p in missing)
        raise FileNotFoundError(f"Missing required files:\n{names}\n\nPlease create them before running.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RFC Spec Reasoning Engine — multi-agent loop to produce the best RFC ticket"
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        default=False,
        help="Disable the Judge agent. Critic is the final authority. "
             "Loop: Generator → Critic → Generator (fix) → ... "
             "Stops when critic APPROVED or max rounds reached.",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=DEFAULT_MAX_ROUNDS,
        metavar="N",
        help=f"Maximum number of review rounds (default: {DEFAULT_MAX_ROUNDS})",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    use_judge = not args.no_judge
    max_rounds = args.rounds

    ensure_files_exist(use_judge)

    mode_label = "Generator → Critic → Judge → fix" if use_judge else "Generator → Critic → fix"
    print(f"RFC Spec Reasoning Engine")
    print(f"Mode     : {'WITH judge' if use_judge else 'NO judge (critic is final authority)'}")
    print(f"Loop     : {mode_label}")
    print(f"Max rounds: {max_rounds}")
    print()

    print("[Init] Clearing previous outputs...")
    write_text(SPEC_FILE, "")
    write_text(REVIEW_FILE, "")
    if use_judge:
        write_text(JUDGE_FILE, "")

    print("[Round 0] Running generator (initial draft)...")
    run_generator(use_judge)
    print("  → rfc_spec.md written")

    for round_number in range(1, max_rounds + 1):
        print(f"\n[Round {round_number}] Running critic...")
        run_critic(use_judge)
        print("  → rfc_review.md written")

        review_text = read_text(REVIEW_FILE)
        review_decision = extract_review_decision(review_text)

        if review_decision == "APPROVED":
            decisions = summarize_state(round_number, use_judge)
            print(f"\nDone: {should_stop(decisions, use_judge)[1]}")
            print(f"Output: {SPEC_FILE}")
            return 0

        if review_decision not in ("APPROVED", "REJECTED"):
            print(
                f"  Warning: critic decision is {review_decision or 'UNKNOWN'} "
                "(expected APPROVED or REJECTED)"
            )

        if use_judge:
            print(f"[Round {round_number}] Running judge...")
            run_judge(use_judge)
            print("  → rfc_judge.md written")

            decisions = summarize_state(round_number, use_judge)
            stop, reason = should_stop(decisions, use_judge)
            if stop:
                exit_code = 1 if decisions.judge_final_decision == "HARD_REJECT" else 0
                print(f"\nDone: {reason}")
                print(f"Output: {SPEC_FILE}")
                return exit_code
        else:
            decisions = summarize_state(round_number, use_judge)

        if round_number >= max_rounds:
            break

        print(f"[Round {round_number}] Running generator (revision)...")
        run_generator(use_judge)
        print("  → rfc_spec.md updated")

    print(f"\nDone: reached max rounds ({max_rounds})")
    print(f"Output: {SPEC_FILE}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
