"""Problem loader for Lean, TeX, Markdown files"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum


class ProblemFormat(Enum):
    LEAN = "lean"
    TEX = "tex"
    MARKDOWN = "md"
    TEXT = "txt"
    UNKNOWN = "unknown"


FORMAT_EXTENSIONS = {
    ".lean": ProblemFormat.LEAN,
    ".tex": ProblemFormat.TEX,
    ".md": ProblemFormat.MARKDOWN,
    ".markdown": ProblemFormat.MARKDOWN,
    ".txt": ProblemFormat.TEXT,
}


@dataclass
class Problem:
    content: str
    format: ProblemFormat
    source_path: Optional[Path] = None
    proof_hint: Optional[str] = None
    context_files: List[Path] = field(default_factory=list)

    @property
    def is_formal(self) -> bool:
        return self.format == ProblemFormat.LEAN

    @property
    def display_name(self) -> str:
        if self.source_path:
            return self.source_path.name
        return f"problem.{self.format.value}"


class ProblemLoader:
    @staticmethod
    def detect_format(path: Path) -> ProblemFormat:
        return FORMAT_EXTENSIONS.get(path.suffix.lower(), ProblemFormat.UNKNOWN)

    @staticmethod
    def load_file(path: Path) -> Problem:
        if not path.exists():
            raise FileNotFoundError(f"Problem file not found: {path}")

        return Problem(
            content=path.read_text(encoding="utf-8"),
            format=ProblemLoader.detect_format(path),
            source_path=path,
        )

    @staticmethod
    def load_with_proof(
        problem_path: Path,
        proof_hint: Optional[str] = None,
        context_paths: Optional[List[Path]] = None,
    ) -> Problem:
        problem = ProblemLoader.load_file(problem_path)
        problem.proof_hint = proof_hint

        if context_paths:
            problem.context_files = [p for p in context_paths if p.exists()]

        return problem

    @staticmethod
    def load_context_folder(folder: Path) -> List[Path]:
        if not folder.exists() or not folder.is_dir():
            return []

        files = []
        for ext in FORMAT_EXTENSIONS:
            files.extend(folder.rglob(f"*{ext}"))
        return sorted(files)

    @staticmethod
    def from_string(
        content: str,
        format_type: ProblemFormat = ProblemFormat.TEXT,
        proof_hint: Optional[str] = None,
    ) -> Problem:
        return Problem(content=content, format=format_type, proof_hint=proof_hint)
