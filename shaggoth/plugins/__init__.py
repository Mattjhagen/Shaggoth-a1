"""Plugin system — the "features I can add" extension point.

A plugin is a function that looks at the user's message and either handles it
(returns a reply string) or passes (returns ``None``). Plugins are checked in
registration order before any generation happens, so they can implement
commands, tools, and integrations.

Registering a feature:

    from shaggoth.plugins import PluginRegistry

    registry = PluginRegistry()

    @registry.register("weather")
    def weather(text, memory=None):
        if "weather" in text.lower():
            return "It's always foggy in the datacenter."
        return None
"""

from __future__ import annotations

from typing import Callable, Optional

PluginFunc = Callable[..., Optional[str]]


class PluginRegistry:
    def __init__(self):
        self._plugins: list[tuple[str, PluginFunc]] = []

    def register(self, name: str):
        def decorator(func: PluginFunc) -> PluginFunc:
            self._plugins.append((name, func))
            return func

        return decorator

    def names(self) -> list[str]:
        return [name for name, _ in self._plugins]

    def dispatch(self, text: str, **context) -> Optional[str]:
        for name, func in self._plugins:
            try:
                result = func(text, **context)
            except Exception as exc:  # noqa: BLE001
                print(f"[plugin:{name}] dispatch failed: {exc}")
                continue
            if result is not None:
                return result
        return None


def default_registry() -> "PluginRegistry":
    from . import builtin

    return builtin.build_registry()


__all__ = ["PluginRegistry", "default_registry"]
