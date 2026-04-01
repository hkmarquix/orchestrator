#!/usr/bin/env python3
"""
Implementation Delivery Engine
Multi-agent loop: Senior Dev → Team Lead Review → Senior Dev (fix) → ... → Handoff

Usage:
    python implementation_orchestrator.py
    python implementation_orchestrator.py --rounds 5

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

SPEC_FILE = BASE_DIR / "rfc_spec.md"
IMPLEMENTATION_REPORT_FILE = BASE_DIR / "implementation_report.md"
CODE_REVIEW_FILE = BASE_DIR / "code_review.md"
HANDOFF_REPORT_FILE = BASE_DIR / "handoff_report.md"

SENIOR_DEV_PROMPT_FILE = PROMPTS_DIR / "senior_dev.txt"
TEAM_LEAD_PROMPT_FILE = PROMPTS_DIR / "team_lead.txt"
HANDOFF_PROMPT_FILE = PROMPTS_DIR / "handoff.txt"

DEFAULT_MAX_ROUNDS = 3


@dataclass
class ImplementationDecisions:
    review_decision: Optional[str] = None
    tests_status: Optional[str] = None
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


def extract_tests_status(text: str) -> Optional[str]:
    match = re.search(r"Tests Status\s*[:：]\s*([^\n]+)", text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


def extract_issues_addressed(text: str) -> Optional[str]:
    match = re.search(r"Issues Addressed\s*[:：]\s*([^\n]+)", text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


def run_command(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return (
            f"[command failed]\n"
            f"$ {' '.join(command)}\n"
            f"exit_code={result.returncode}\n"
            f"stdout:\n{result.stdout.strip()}\n"
            f"stderr:\n{result.stderr.strip()}"
        )
    return result.stdout.strip()


def gather_workspace_context() -> str:
    status = run_command(["git", "status", "--short"])
    tracked_files = run_command(["rg", "--files"])
    return (
        "=======================\n"
        "WORKSPACE SNAPSHOT\n"
        "=======================\n\n"
        "[git status --short]\n"
        f"{status or '(clean)'}\n\n"
        "[rg --files]\n"
        f"{tracked_files or '(no files found)'}"
    )


def build_prompt(
    role_prompt: str,
    *,
    spec: str,
    implementation_report: str,
    code_review: str,
    handoff_report: str,
    include_handoff_context: bool = False,
) -> str:
    handoff_block = (
        f"\n[FILE: handoff_report.md]\n"
        f"{handoff_report if handoff_report else '(missing)'}"
        if include_handoff_context
        else ""
    )

    return f"""{role_prompt}

=======================
SOURCE OF TRUTH FILES
=======================

[FILE: rfc_spec.md]
{spec if spec else '(missing)'}

[FILE: implementation_report.md]
{implementation_report if implementation_report else '(missing)'}

[FILE: code_review.md]
{code_review if code_review else '(missing)'}{handoff_block}

{gather_workspace_context()}

=======================
TASK EXECUTION RULES
=======================

- Read the files above as the current source of truth.
- Inspect the repository directly before making claims about implementation status.
- You may edit source files in the workspace if your role requires it.
- You may run tests, linters, and other verification commands if your role requires it.
- Output ONLY the full content of the file requested by your role.
- Do not add any explanation or commentary outside the file content.
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


def run_senior_dev() -> None:
    role_prompt = require_file(SENIOR_DEV_PROMPT_FILE)
    prompt = build_prompt(
        role_prompt,
        spec=require_file(SPEC_FILE),
        implementation_report=read_text(IMPLEMENTATION_REPORT_FILE),
        code_review=read_text(CODE_REVIEW_FILE),
        handoff_report=read_text(HANDOFF_REPORT_FILE),
    )
    output = call_model(prompt)
    write_text(IMPLEMENTATION_REPORT_FILE, output)


def run_team_lead() -> None:
    role_prompt = require_file(TEAM_LEAD_PROMPT_FILE)
    prompt = build_prompt(
        role_prompt,
        spec=require_file(SPEC_FILE),
        implementation_report=read_text(IMPLEMENTATION_REPORT_FILE),
        code_review=read_text(CODE_REVIEW_FILE),
        handoff_report=read_text(HANDOFF_REPORT_FILE),
    )
    output = call_model(prompt)
    write_text(CODE_REVIEW_FILE, output)


def run_handoff() -> None:
    role_prompt = require_file(HANDOFF_PROMPT_FILE)
    prompt = build_prompt(
        role_prompt,
        spec=require_file(SPEC_FILE),
        implementation_report=read_text(IMPLEMENTATION_REPORT_FILE),
        code_review=read_text(CODE_REVIEW_FILE),
        handoff_report=read_text(HANDOFF_REPORT_FILE),
        include_handoff_context=True,
    )
    output = call_model(prompt)
    write_text(HANDOFF_REPORT_FILE, output)


def summarize_state(round_number: int) -> ImplementationDecisions:
    implementation_text = read_text(IMPLEMENTATION_REPORT_FILE)
    review_text = read_text(CODE_REVIEW_FILE)

    decisions = ImplementationDecisions(
        review_decision=extract_review_decision(review_text),
        tests_status=extract_tests_status(review_text),
        issues_addressed=extract_issues_addressed(implementation_text),
    )

    print(f"\n=== Round {round_number} Summary ===")
    print(f"Review decision  : {decisions.review_decision or 'UNKNOWN'}")
    print(f"Tests status     : {decisions.tests_status or 'N/A'}")
    print(f"Issues addressed : {decisions.issues_addressed or 'N/A'}")
    return decisions


def ensure_files_exist() -> None:
    required = [SPEC_FILE, SENIOR_DEV_PROMPT_FILE, TEAM_LEAD_PROMPT_FILE, HANDOFF_PROMPT_FILE]
    missing = [p for p in required if not p.exists()]
    if missing:
        names = "\n".join(f"  - {p}" for p in missing)
        raise FileNotFoundError(f"Missing required files:\n{names}\n\nPlease create them before running.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Implementation Delivery Engine — senior dev coding loop with team lead approval"
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=DEFAULT_MAX_ROUNDS,
        metavar="N",
        help=f"Maximum number of implementation review rounds (default: {DEFAULT_MAX_ROUNDS})",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    max_rounds = args.rounds

    ensure_files_exist()

    print("Implementation Delivery Engine")
    print("Loop      : Senior Dev → Team Lead Review → fix → ... → Handoff")
    print("Stop      : Team lead APPROVED, then handoff report is written")
    print(f"Max rounds: {max_rounds}")
    print()

    print("[Init] Clearing previous implementation artifacts...")
    write_text(IMPLEMENTATION_REPORT_FILE, "")
    write_text(CODE_REVIEW_FILE, "")
    write_text(HANDOFF_REPORT_FILE, "")

    print("[Round 0] Running senior dev (initial implementation)...")
    run_senior_dev()
    print("  → implementation_report.md written")

    for round_number in range(1, max_rounds + 1):
        print(f"\n[Round {round_number}] Running team lead review...")
        run_team_lead()
        print("  → code_review.md written")

        decisions = summarize_state(round_number)
        if decisions.review_decision == "APPROVED":
            print(f"[Round {round_number}] Running senior dev handoff...")
            run_handoff()
            print("  → handoff_report.md written")
            print("\nDone: team lead approved implementation")
            print(f"Outputs: {IMPLEMENTATION_REPORT_FILE}, {CODE_REVIEW_FILE}, {HANDOFF_REPORT_FILE}")
            return 0

        if decisions.review_decision not in ("APPROVED", "CHANGES_REQUESTED", "REJECTED"):
            print(
                f"  Warning: team lead decision is {decisions.review_decision or 'UNKNOWN'} "
                "(expected APPROVED, CHANGES_REQUESTED, or REJECTED)"
            )

        if round_number >= max_rounds:
            break

        print(f"[Round {round_number}] Running senior dev (revision)...")
        run_senior_dev()
        print("  → implementation_report.md updated")

    print(f"\nDone: reached max rounds ({max_rounds}) without approval")
    print(f"Latest artifacts: {IMPLEMENTATION_REPORT_FILE}, {CODE_REVIEW_FILE}")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
