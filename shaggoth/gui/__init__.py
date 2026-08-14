"""Desktop GUI for Shaggoth.

``shaggoth gui`` launches a Tkinter chat window. The window itself is a thin
view over :class:`.core.GUIController`, which is Tk-free and unit-tested; on
machines without Tkinter the command prints install instructions and exits
rather than failing mysteriously.
"""

from .core import GUIController, Turn

__all__ = ["GUIController", "Turn"]
