"""
Models used by the execution layers.

Splitting these dataclasses into their own module keeps executor.py focused
on execution strategies instead of data container definitions.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union


@dataclass
class ExecutionConfig:
    """Configuration for test execution."""
    command: Union[str, List[str]]
    working_dir: str = "."
    env: Dict[str, str] = field(default_factory=dict)
    timeout: Optional[int] = None
    shell: bool = True
    stream_output: bool = True
    capture_output: bool = True
    fail_fast: bool = True


@dataclass
class ExecutionResult:
    """Result of test execution."""
    exit_code: int
    stdout: str
    stderr: str
    duration: float
    command: str

    @property
    def success(self) -> bool:
        return self.exit_code == 0
