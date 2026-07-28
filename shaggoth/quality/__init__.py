"""Judging Shaggoth's own answers, so quality does not depend on a human noticing."""

from .teacher import Teacher, TeacherVerdict
from .critic import CriticLoop

__all__ = ["CriticLoop", "Teacher", "TeacherVerdict"]
