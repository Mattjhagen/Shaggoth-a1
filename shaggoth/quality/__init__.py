"""Judging Shaggoth's own answers, so quality does not depend on a human noticing."""

from .teacher import (
    AnthropicTeacher,
    FallbackTeacher,
    OpenRouterTeacher,
    Teacher,
    TeacherVerdict,
    build_teacher,
)
from .critic import CriticLoop

__all__ = [
    "AnthropicTeacher",
    "CriticLoop",
    "FallbackTeacher",
    "OpenRouterTeacher",
    "Teacher",
    "TeacherVerdict",
    "build_teacher",
]
