"""Curiosity engine — autonomous knowledge acquisition.

Detects knowledge gaps from user messages, searches the web, scrapes
relevant pages, and feeds learned content into the knowledge base.
"""

from .engine import CuriosityEngine

__all__ = ["CuriosityEngine"]
