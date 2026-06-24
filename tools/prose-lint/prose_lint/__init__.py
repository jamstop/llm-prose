"""Deterministic, AST-based linter for the mechanical half of the comment rubric."""

from .model import Finding
from .core import lint_source, lint_path

__all__ = ["Finding", "lint_source", "lint_path"]
