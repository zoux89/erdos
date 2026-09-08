"""Main pipeline for proof solving"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime
from enum import Enum

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.markdown import Markdown

from .Config import Config
from .ProblemLoader import Problem
from .AristotleClient import AristotleClient, ProofResult
from .LeanVerifier import LeanVerifier, VerificationResult, VerificationStatus
from .LLMJudge import LLMJudge, JudgeFeedback


class PipelineState(Enum):
    INITIALIZING = "initializing"
    LOADING_PROBLEM = "loading_problem"
    GENERATING_PROOF = "generating_proof"
    VERIFYING_PROOF = "verifying_proof"
    ANALYZING_FAILURE = "analyzing_failure"
    RETRYING = "retrying"
    SUCCESS = "success"
    FAILED = "failed"


STATE_COLORS = {
    PipelineState.INITIALIZING: "dim",
    PipelineState.LOADING_PROBLEM: "blue",
    PipelineState.GENERATING_PROOF: "yellow",
    PipelineState.VERIFYING_PROOF: "cyan",
    PipelineState.ANALYZING_FAILURE: "magenta",
    PipelineState.RETRYING: "yellow",
    PipelineState.SUCCESS: "green",
    PipelineState.FAILED: "red",
}


@dataclass
class PipelineAttempt:
    attempt_number: int
    proof_hint: Optional[str]
    proof_result: Optional[ProofResult]
    verification_result: Optional[VerificationResult]
    judge_feedback: Optional[JudgeFeedback]
    timestamp: datetime = field(default_factory=datetime.now)
    llm_logic_check: Optional[dict] = None
    llm_feedback_for_retry: Optional[str] = None


@dataclass
class PipelineResult:
    success: bool
    problem: Problem
    final_proof: Optional[str] = None
    solution_path: Optional[Path] = None
    attempts: List[PipelineAttempt] = field(default_factory=list)
    total_time_seconds: float = 0.0

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)


class Pipeline:
    def __init__(self, config: Config, console: Optional[Console] = None):
        self.config = config
        self.console = console or Console()

        self.aristotle = AristotleClient(
            api_key=config.aristotle_api_key,
            polling_interval=config.polling_interval_seconds,
            console=self.console,
        )

        self.verifier = LeanVerifier(
            timeout_seconds=config.lean_timeout_seconds,
            console=self.console,
        )

        self.judge = None
        if config.anthropic_api_key:
            self.judge = LLMJudge(api_key=config.anthropic_api_key, model=config.llm_model)

        self.state = PipelineState.INITIALIZING
        self.attempts: List[PipelineAttempt] = []
        self.skip_verification = False

    def _update_state(self, state: PipelineState):
        self.state = state
        color = STATE_COLORS.get(state, "white")
        text = state.value.replace("_", " ").title()
        self.console.print(f"  [{color}]● {text}[/{color}]")

    async def run(
        self,
        problem: Problem,
        output_path: Optional[Path] = None,
        skip_verification: bool = False,
    ) -> PipelineResult:
        self.skip_verification = skip_verification
        if skip_verification:
            self.console.print("[yellow]⚠ Skipping Lean verification (--no-verify)[/yellow]")

        start_time = datetime.now()
        self.attempts = []
        current_hint = problem.proof_hint

        self._display_problem_header(problem)

        for attempt_num in range(1, self.config.max_iterations + 1):
            self.console.print(f"\n[bold]Attempt {attempt_num}/{self.config.max_iterations}[/bold]")

            attempt = await self._run_attempt(problem, attempt_num, current_hint, output_path)
            self.attempts.append(attempt)

            proof_ok = attempt.proof_result and attempt.proof_result.success
            verified = attempt.verification_result and attempt.verification_result.success

            if proof_ok and (verified or skip_verification):
                self._update_state(PipelineState.SUCCESS)
                self._display_success(attempt, skip_verification)
                elapsed = (datetime.now() - start_time).total_seconds()
                return PipelineResult(
                    success=True,
                    problem=problem,
                    final_proof=attempt.proof_result.solution_content,
                    solution_path=attempt.proof_result.solution_path,
                    attempts=self.attempts,
                    total_time_seconds=elapsed,
                )

            if not self.judge or attempt_num >= self.config.max_iterations:
                continue

            self._update_state(PipelineState.ANALYZING_FAILURE)

            # Use BS proof feedback if available
            if attempt.llm_feedback_for_retry:
                self.console.print("[magenta]Using LLM feedback for BS proof...[/magenta]")
                current_hint = f"IMPORTANT: Previous proof used trivial/degenerate case. {attempt.llm_feedback_for_retry}\n\nOriginal: {current_hint or 'None'}"
                self._update_state(PipelineState.RETRYING)
                continue

            error_output = ""
            if attempt.verification_result:
                error_output = attempt.verification_result.error_summary
            elif attempt.proof_result and attempt.proof_result.error_message:
                error_output = attempt.proof_result.error_message

            feedback = await self.judge.analyze_failure(
                problem=problem.content,
                proof_hint=current_hint,
                generated_proof=attempt.proof_result.solution_content if attempt.proof_result else None,
                error_output=error_output,
                attempt_number=attempt_num,
            )

            attempt.judge_feedback = feedback
            self._display_feedback(feedback)

            if not feedback.should_retry:
                self.console.print("[yellow]Judge recommends not retrying.[/yellow]")
                break

            if feedback.revised_proof_hint:
                current_hint = feedback.revised_proof_hint
                self._update_state(PipelineState.RETRYING)

        self._update_state(PipelineState.FAILED)
        self._display_failure()

        elapsed = (datetime.now() - start_time).total_seconds()
        return PipelineResult(success=False, problem=problem, attempts=self.attempts, total_time_seconds=elapsed)

    async def _run_attempt(
        self,
        problem: Problem,
        attempt_number: int,
        proof_hint: Optional[str],
        output_path: Optional[Path],
    ) -> PipelineAttempt:
        attempt = PipelineAttempt(
            attempt_number=attempt_number,
            proof_hint=proof_hint,
            proof_result=None,
            verification_result=None,
            judge_feedback=None,
        )

        self._update_state(PipelineState.GENERATING_PROOF)

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=self.console, transient=True) as progress:
            progress.add_task("Generating proof with Aristotle...", total=None)
            proof_result = await self.aristotle.prove(
                content=problem.content,
                is_formal=problem.is_formal,
                proof_hint=proof_hint,
                context_files=problem.context_files,
                output_path=output_path,
                source_path=problem.source_path,
            )

        attempt.proof_result = proof_result

        if not proof_result.success:
            self.console.print(f"[red]✗ Proof generation failed: {proof_result.error_message}[/red]")
            return attempt

        self.console.print("[green]✓ Proof generated[/green]")

        if self.skip_verification:
            self.console.print("[dim]⏭ Skipping Lean verification[/dim]")
            return attempt

        if not proof_result.solution_content:
            return attempt

        self._update_state(PipelineState.VERIFYING_PROOF)

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=self.console, transient=True) as progress:
            progress.add_task("Verifying proof with Lean...", total=None)
            verification_result = await self.verifier.verify_content(proof_result.solution_content)

        attempt.verification_result = verification_result

        if not verification_result.success:
            self.console.print("[red]✗ Verification failed[/red]")
            for err in verification_result.errors[:3]:
                self.console.print(f"  [dim]{err}[/dim]")
            return attempt

        self.console.print("[green]✓ Proof verified by Lean[/green]")

        # LLM sanity check
        if not self.judge:
            return attempt

        self.console.print("[cyan]🔍 LLM Judge checking if proof is legitimate...[/cyan]")
        logic_check = await self.judge.verify_proof_logic(proof_result.solution_content, problem.content)
        attempt.llm_logic_check = logic_check
        is_real = logic_check.get("is_real_proof", True)

        if is_real:
            self.console.print(Panel(
                f"[bold green]✓ PROOF IS LEGITIMATE[/bold green]\n\n"
                f"[bold]Summary:[/bold] {logic_check.get('summary', 'N/A')}\n"
                f"[dim]Confidence: {logic_check.get('confidence', 0) * 100:.0f}%[/dim]",
                title="[green]LLM Verdict: PASS[/green]",
                border_style="green",
            ))
            return attempt

        issues = logic_check.get("issues", [])
        issues_str = "\n".join(f"  • {i}" for i in issues[:5]) if issues else "  None"
        feedback = logic_check.get("feedback", "")

        self.console.print(Panel(
            f"[bold red]✗ BS PROOF DETECTED[/bold red]\n\n"
            f"[bold]Summary:[/bold] {logic_check.get('summary', 'N/A')}\n\n"
            f"[bold]Issues:[/bold]\n{issues_str}\n\n"
            f"[bold]Feedback:[/bold]\n{feedback}",
            title="[red]LLM Verdict: FAIL[/red]",
            border_style="red",
        ))

        verification_result.status = VerificationStatus.ERROR
        verification_result.errors.append(f"LLM: {logic_check.get('summary', 'BS proof')}")
        attempt.llm_feedback_for_retry = feedback

        return attempt

    def _display_problem_header(self, problem: Problem):
        self.console.print()
        self.console.print(Panel(
            f"[bold]{problem.display_name}[/bold]\n"
            f"Format: {problem.format.value.upper()}\n"
            f"Context files: {len(problem.context_files)}",
            title="[cyan]Problem[/cyan]",
            border_style="cyan",
        ))

        if problem.proof_hint:
            hint = problem.proof_hint[:500] + ("..." if len(problem.proof_hint) > 500 else "")
            self.console.print(Panel(hint, title="[yellow]Proof Hint[/yellow]", border_style="yellow"))

    def _display_success(self, attempt: PipelineAttempt, skipped: bool = False):
        self.console.print()

        if skipped:
            msg = "[bold yellow]✓ PROOF GENERATED (not verified)[/bold yellow]\n\nUse 'erdos check <proof.lean>' to verify later.\n\n"
        else:
            msg = "[bold green]✓ PROOF VERIFIED SUCCESSFULLY[/bold green]\n\n"

        msg += f"Attempts: {attempt.attempt_number}\n"
        msg += f"Solution: {attempt.proof_result.solution_path if attempt.proof_result else 'N/A'}"

        title = "[yellow]Generated[/yellow]" if skipped else "[green]Success[/green]"
        color = "yellow" if skipped else "green"
        self.console.print(Panel(msg, title=title, border_style=color))

        if attempt.proof_result and attempt.proof_result.solution_content:
            content = attempt.proof_result.solution_content
            if len(content) > 1000:
                content = content[:1000] + "\n... (truncated)"
            self.console.print()
            self.console.print(Syntax(content, "lean", theme="monokai", line_numbers=True))

    def _display_failure(self):
        self.console.print()
        self.console.print(Panel(
            f"[bold red]✗ PROOF FAILED[/bold red]\n\nExhausted all {len(self.attempts)} attempts.",
            title="[red]Failed[/red]",
            border_style="red",
        ))

    def _display_feedback(self, feedback: JudgeFeedback):
        self.console.print()
        self.console.print(Panel(
            Markdown(f"**Analysis:**\n{feedback.analysis}\n\n**Suggestions:**\n{feedback.suggestions}"),
            title="[magenta]LLM Judge Feedback[/magenta]",
            border_style="magenta",
        ))
