"""Untrusted language interpretation; no SQL, execution, or answer generation."""

from backend.interpretation.service import InterpretationResult, Interpreter

__all__ = ["InterpretationResult", "Interpreter"]
