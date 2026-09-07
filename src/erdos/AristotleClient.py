"""Aristotle API client wrapper"""

import asyncio
import os
import tempfile
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum

from rich.console import Console
from rich.live import Live
from rich.text import Text


class ProofStatus(Enum):
    NOT_STARTED = "not_started"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class ProofResult:
    status: ProofStatus
    solution_path: Optional[Path] = None
    solution_content: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.status == ProofStatus.COMPLETE and self.solution_content is not None


class AristotleClient:
    def __init__(self, api_key: str, polling_interval: int = 10, console: Optional[Console] = None):
        self.api_key = api_key
        self.polling_interval = polling_interval
        self.console = console or Console()
        os.environ["ARISTOTLE_API_KEY"] = api_key

    async def prove(
        self,
        content: str,
        is_formal: bool = False,
        proof_hint: Optional[str] = None,
        context_files: Optional[List[Path]] = None,
        output_path: Optional[Path] = None,
        source_path: Optional[Path] = None,
    ) -> ProofResult:
        """Submit a problem to Aristotle for proving."""
        from aristotlelib import Project, ProjectInputType

        if is_formal and source_path and source_path.exists():
            input_path = source_path
            input_type = ProjectInputType.FORMAL_LEAN
        else:
            full_content = content
            if proof_hint:
                full_content = f"{content}\n\nPROVIDED SOLUTION:\n{proof_hint}"

            fd, temp_path_str = tempfile.mkstemp(suffix='.txt')
            os.close(fd)
            input_path = Path(temp_path_str)
            input_path.write_text(full_content)
            input_type = ProjectInputType.INFORMAL

        self.console.print("Creating Aristotle project...")
        start_time = time.time()

        proof_coro = Project.prove_from_file(
            input_file_path=str(input_path),
            output_file_path=str(output_path) if output_path else None,
            project_input_type=input_type,
            context_file_paths=[str(p) for p in context_files] if context_files else None,
            wait_for_completion=True,
            polling_interval_seconds=self.polling_interval,
        )

        proof_task = asyncio.create_task(proof_coro)

        with Live(console=self.console, refresh_per_second=2) as live:
            while not proof_task.done():
                elapsed = time.time() - start_time
                mins, secs = int(elapsed // 60), int(elapsed % 60)

                status_text = Text()
                status_text.append("⏳ ", style="yellow")
                status_text.append("Aristotle working... ", style="cyan")
                status_text.append(f"{mins:02d}:{secs:02d}", style="bold yellow")
                status_text.append(" elapsed", style="dim")

                live.update(status_text)
                await asyncio.sleep(0.5)

        # Clean up temp file if we created one
        if not is_formal:
            input_path.unlink(missing_ok=True)

        result_path = await proof_task
        elapsed = time.time() - start_time
        self.console.print(f"[dim]Aristotle finished in {elapsed:.1f}s[/dim]")

        if not result_path:
            return ProofResult(status=ProofStatus.FAILED, error_message="No result path returned")

        result_file = Path(result_path)
        if not result_file.exists():
            return ProofResult(status=ProofStatus.FAILED, error_message=f"Result file not found: {result_path}")

        solution_content = result_file.read_text()
        return ProofResult(
            status=ProofStatus.COMPLETE,
            solution_path=result_file,
            solution_content=solution_content,
        )
