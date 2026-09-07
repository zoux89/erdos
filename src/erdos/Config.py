"""Configuration for Erdos pipeline"""

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


@dataclass
class Config:
    aristotle_api_key: str
    anthropic_api_key: Optional[str] = None
    llm_model: str = "claude-sonnet-4-20250514"
    max_iterations: int = 5
    polling_interval_seconds: int = 30
    lean_timeout_seconds: int = 300
    problems_dir: Path = Path("./problems")
    solutions_dir: Path = Path("./solutions")
    logs_dir: Path = Path("./logs")

    @classmethod
    def from_env(cls, env_file: Optional[Path] = None) -> "Config":
        if env_file and env_file.exists():
            load_dotenv(env_file)
        else:
            load_dotenv()

        aristotle_key = os.getenv("ARISTOTLE_API_KEY")
        if not aristotle_key:
            raise ValueError("ARISTOTLE_API_KEY not set")

        return cls(
            aristotle_api_key=aristotle_key,
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            llm_model=os.getenv("LLM_MODEL", "claude-sonnet-4-20250514"),
            max_iterations=int(os.getenv("MAX_ITERATIONS", "5")),
            polling_interval_seconds=int(os.getenv("POLLING_INTERVAL_SECONDS", "30")),
            lean_timeout_seconds=int(os.getenv("LEAN_TIMEOUT_SECONDS", "300")),
            problems_dir=Path(os.getenv("PROBLEMS_DIR", "./problems")),
            solutions_dir=Path(os.getenv("SOLUTIONS_DIR", "./solutions")),
            logs_dir=Path(os.getenv("LOGS_DIR", "./logs")),
        )
