"""CLI for Erdos proof pipeline"""

import asyncio
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .Config import Config
from .ProblemLoader import ProblemLoader
from .Pipeline import Pipeline

app = typer.Typer(name="erdos", help="Erdos - Mathematical proof pipeline", add_completion=False)
console = Console()


BANNER = """
[bold cyan]
    ███████╗██████╗ ██████╗  ██████╗ ███████╗
    ██╔════╝██╔══██╗██╔══██╗██╔═══██╗██╔════╝
    █████╗  ██████╔╝██║  ██║██║   ██║███████╗
    ██╔══╝  ██╔══██╗██║  ██║██║   ██║╚════██║
    ███████╗██║  ██║██████╔╝╚██████╔╝███████║
    ╚══════╝╚═╝  ╚═╝╚═════╝  ╚═════╝ ╚══════╝
[/bold cyan]
[dim]    Mathematical Proof Pipeline powered by Aristotle[/dim]
"""


def print_banner():
    console.print(BANNER)


def mask_secret(secret: Optional[str]) -> str:
    if not secret:
        return "[dim]Not set[/dim]"
    if len(secret) <= 8:
        return "*" * len(secret)
    return secret[:4] + "*" * (len(secret) - 8) + secret[-4:]


@app.command("prove")
def prove(
    problem: Path = typer.Argument(..., help="Problem file (Lean, TeX, MD)", exists=True),
    proof: Optional[str] = typer.Option(None, "--proof", "-p", help="Proof hint"),
    proof_file: Optional[Path] = typer.Option(None, "--proof-file", "-P", exists=True),
    context: Optional[List[Path]] = typer.Option(None, "--context", "-c"),
    context_folder: Optional[Path] = typer.Option(None, "--context-folder", "-C", exists=True, dir_okay=True, file_okay=False),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
    max_iterations: int = typer.Option(5, "--max-iterations", "-n"),
    env_file: Optional[Path] = typer.Option(None, "--env", "-e"),
    no_verify: bool = typer.Option(False, "--no-verify"),
):
    """Prove a mathematical problem using Aristotle API."""
    print_banner()

    try:
        config = Config.from_env(env_file)
    except ValueError as e:
        console.print(f"[red]Config error: {e}[/red]")
        console.print("[dim]Set ARISTOTLE_API_KEY in environment or .env[/dim]")
        raise typer.Exit(1)

    config.max_iterations = max_iterations

    proof_hint = proof
    if proof_file:
        proof_hint = proof_file.read_text()

    context_files = list(context) if context else []
    if context_folder:
        context_files.extend(ProblemLoader.load_context_folder(context_folder))

    console.print("[cyan]Loading problem...[/cyan]")
    problem_obj = ProblemLoader.load_with_proof(problem, proof_hint, context_files)

    if context_files:
        table = Table(title="Context Files")
        table.add_column("File", style="cyan")
        table.add_column("Type", style="green")
        for cf in context_files:
            table.add_row(cf.name, cf.suffix.upper())
        console.print(table)

    pipeline = Pipeline(config, console)
    result = asyncio.run(pipeline.run(problem_obj, output, no_verify))

    console.print()
    if result.success:
        console.print(Panel(
            f"[bold green]✓ Proof completed![/bold green]\n\n"
            f"Attempts: {result.attempt_count}\n"
            f"Time: {result.total_time_seconds:.1f}s\n"
            f"Solution: {result.solution_path or 'In memory'}",
            title="[green]Summary[/green]",
            border_style="green",
        ))
        raise typer.Exit(0)

    console.print(Panel(
        f"[bold red]✗ Proof failed[/bold red]\n\n"
        f"Attempts: {result.attempt_count}\n"
        f"Time: {result.total_time_seconds:.1f}s",
        title="[red]Summary[/red]",
        border_style="red",
    ))
    raise typer.Exit(1)


@app.command("check")
def check(proof: Path = typer.Argument(..., help="Lean proof file", exists=True)):
    """Verify a Lean proof locally."""
    print_banner()

    from .LeanVerifier import LeanVerifier

    console.print(f"[cyan]Verifying {proof.name}...[/cyan]")
    verifier = LeanVerifier()
    result = asyncio.run(verifier.verify_file(proof))

    if result.success:
        console.print(Panel("[bold green]✓ Proof is valid![/bold green]", title="[green]Result[/green]", border_style="green"))
        for w in result.warnings:
            console.print(f"  [dim]{w}[/dim]")
        raise typer.Exit(0)

    console.print(Panel("[bold red]✗ Verification failed[/bold red]", title="[red]Result[/red]", border_style="red"))
    for e in result.errors:
        console.print(f"  {e}")
    raise typer.Exit(1)


@app.command("batch")
def batch(
    folder: Path = typer.Argument(..., help="Folder with problems", exists=True, dir_okay=True, file_okay=False),
    output_folder: Optional[Path] = typer.Option(None, "--output", "-o"),
    pattern: str = typer.Option("*.lean", "--pattern", "-p"),
    max_iterations: int = typer.Option(3, "--max-iterations", "-n"),
):
    """Process multiple problems from a folder."""
    print_banner()

    try:
        config = Config.from_env()
    except ValueError as e:
        console.print(f"[red]Config error: {e}[/red]")
        raise typer.Exit(1)

    config.max_iterations = max_iterations

    problems = list(folder.glob(pattern))
    if not problems:
        console.print(f"[yellow]No files matching '{pattern}' in {folder}[/yellow]")
        raise typer.Exit(0)

    console.print(f"[cyan]Found {len(problems)} problems[/cyan]")

    if output_folder:
        output_folder.mkdir(parents=True, exist_ok=True)

    results = []
    pipeline = Pipeline(config, console)

    for i, path in enumerate(problems, 1):
        console.print(f"\n[bold]Processing {i}/{len(problems)}: {path.name}[/bold]")
        problem = ProblemLoader.load_file(path)
        out = output_folder / f"{path.stem}_solved.lean" if output_folder else None
        result = asyncio.run(pipeline.run(problem, out))
        results.append((path, result))

    console.print()
    table = Table(title="Batch Results")
    table.add_column("Problem", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Attempts", justify="right")
    table.add_column("Time", justify="right")

    success_count = 0
    for path, result in results:
        status = "[green]✓[/green]" if result.success else "[red]✗[/red]"
        if result.success:
            success_count += 1
        table.add_row(path.name, status, str(result.attempt_count), f"{result.total_time_seconds:.1f}s")

    console.print(table)
    console.print(f"\n[bold]Success: {success_count}/{len(problems)} ({100 * success_count / len(problems):.0f}%)[/bold]")


@app.command("config")
def show_config(env_file: Optional[Path] = typer.Option(None, "--env", "-e")):
    """Show current configuration."""
    print_banner()

    try:
        config = Config.from_env(env_file)
    except ValueError as e:
        console.print(f"[red]Config error: {e}[/red]")
        console.print("\n[yellow]Required:[/yellow] ARISTOTLE_API_KEY")
        console.print("[yellow]Optional:[/yellow] ANTHROPIC_API_KEY, LLM_MODEL, MAX_ITERATIONS")
        raise typer.Exit(1)

    table = Table(title="Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Aristotle API Key", mask_secret(config.aristotle_api_key))
    table.add_row("Anthropic API Key", mask_secret(config.anthropic_api_key) if config.anthropic_api_key else "[dim]Not set[/dim]")
    table.add_row("LLM Model", config.llm_model)
    table.add_row("Max Iterations", str(config.max_iterations))
    table.add_row("Polling Interval", f"{config.polling_interval_seconds}s")
    table.add_row("Lean Timeout", f"{config.lean_timeout_seconds}s")

    console.print(table)


@app.callback()
def main():
    """Erdos - Mathematical Proof Pipeline"""
    pass


def run():
    app()


if __name__ == "__main__":
    run()
