"""Lean proof verifier using local Mathlib project"""

import asyncio
import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum

from rich.console import Console
from rich.panel import Panel


class VerificationStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ERROR = "error"
    HAS_SORRY = "has_sorry"


@dataclass
class VerificationResult:
    status: VerificationStatus
    output: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.status == VerificationStatus.SUCCESS

    @property
    def error_summary(self) -> str:
        if not self.errors:
            return self.output
        return "\n".join(self.errors)


class LeanVerifier:
    def __init__(self, timeout_seconds: int = 300, console: Optional[Console] = None):
        self.timeout = timeout_seconds
        self.console = console or Console()
        self.project_root = self._find_project_root()

        elan_bin = Path.home() / ".elan" / "bin"
        if elan_bin.exists():
            os.environ["PATH"] = f"{elan_bin}:{os.environ.get('PATH', '')}"

    def _find_project_root(self) -> Optional[Path]:
        candidates = [
            Path.cwd(),
            Path(__file__).parent.parent.parent.parent,
            Path.home() / "Projects" / "erdos",
        ]
        for candidate in candidates:
            if (candidate / "lakefile.toml").exists():
                return candidate
        return None

    def _has_sorry(self, content: str) -> bool:
        for line in content.splitlines():
            if line.strip().startswith("--"):
                continue
            if "sorry" in line:
                return True
        return False

    def _parse_output(self, output: str) -> tuple[List[str], List[str]]:
        errors, warnings = [], []
        for line in output.splitlines():
            lower = line.lower()
            if "error:" in lower:
                errors.append(line.strip())
            elif "warning:" in lower:
                warnings.append(line.strip())
            elif "declaration uses 'sorry'" in lower:
                warnings.append("Proof contains sorry (incomplete)")
        return errors, warnings

    async def verify_file(self, lean_file: Path) -> VerificationResult:
        if not lean_file.exists():
            return VerificationResult(
                status=VerificationStatus.ERROR,
                output=f"File not found: {lean_file}",
                errors=[f"File not found: {lean_file}"],
            )

        content = lean_file.read_text()
        if self._has_sorry(content):
            self.console.print("[yellow]⚠ Proof contains 'sorry' (incomplete)[/yellow]")
            return VerificationResult(
                status=VerificationStatus.HAS_SORRY,
                output="Proof contains sorry statements",
                warnings=["Proof is incomplete (contains sorry)"],
            )

        return await self._run_lake_build(lean_file)

    async def verify_content(self, content: str, filename: str = "Verify") -> VerificationResult:
        if not self.project_root:
            return VerificationResult(
                status=VerificationStatus.ERROR,
                output="Erdos project not found",
                errors=["Project root not found"],
            )

        if self._has_sorry(content):
            self.console.print("[yellow]⚠ Proof contains 'sorry' (incomplete)[/yellow]")
            return VerificationResult(
                status=VerificationStatus.HAS_SORRY,
                output="Proof contains sorry statements",
                warnings=["Proof is incomplete (contains sorry)"],
            )

        solutions_dir = self.project_root / "solutions"
        solutions_dir.mkdir(exist_ok=True)
        temp_file = solutions_dir / f"{filename}.lean"
        temp_file.write_text(content)

        result = await self._run_lake_build(temp_file)
        temp_file.unlink(missing_ok=True)
        return result

    async def _run_lake_build(self, lean_file: Path) -> VerificationResult:
        if not self.project_root:
            return VerificationResult(
                status=VerificationStatus.ERROR,
                output="Lean project not found",
                errors=["No lakefile.toml found"],
            )

        rel_path = lean_file.relative_to(self.project_root)
        module_name = str(rel_path.with_suffix("")).replace("/", ".").replace("\\", ".")
        self.console.print(f"[cyan]Building {module_name}...[/cyan]")

        process = await asyncio.create_subprocess_exec(
            "lake", "build", module_name,
            cwd=str(self.project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ},
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
        except asyncio.TimeoutError:
            process.kill()
            return VerificationResult(
                status=VerificationStatus.TIMEOUT,
                output=f"Verification timed out after {self.timeout}s",
                errors=[f"Timeout after {self.timeout}s"],
            )

        output = stdout.decode() + stderr.decode()
        errors, warnings = self._parse_output(output)

        if process.returncode == 0 and not errors:
            self.console.print(Panel(
                "[bold green]✓ PROOF VERIFIED BY LEAN[/bold green]\n\n"
                "The proof type-checks correctly.\n"
                "All logical steps are valid.",
                title="[green]Lean Verification[/green]",
                border_style="green",
            ))
            return VerificationResult(status=VerificationStatus.SUCCESS, output=output, warnings=warnings)

        self.console.print(Panel(
            f"[bold red]✗ VERIFICATION FAILED[/bold red]\n\nErrors: {len(errors)}",
            title="[red]Lean Verification[/red]",
            border_style="red",
        ))
        for err in errors[:5]:
            self.console.print(f"  [red]• {err}[/red]")

        return VerificationResult(status=VerificationStatus.FAILED, output=output, errors=errors, warnings=warnings)
