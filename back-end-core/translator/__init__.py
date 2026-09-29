"""Local, rule-first translation of diary/chat text into evidence-linked cues.

The vocabulary is deliberately small and provisional. No diagnosis, stable
personality trait, or trained model is produced by this package.
"""

from .pipeline import summarize, translate

__all__ = ["translate", "summarize"]
