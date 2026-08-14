"""Tkinter shell for the Shaggoth GUI. Imports tkinter lazily so the rest of
the package (and the test suite) works on machines with no Tk at all.
"""

from __future__ import annotations


def run_tk_app(engine, supervisor=None) -> int:
    """Launch the desktop chat window. Exits 1 with a message when Tk is missing.

    *supervisor* is an optional :class:`~shaggoth.agents.Supervisor`; when
    given, the window grows a training panel showing what the crew is doing.
    """
    try:
        import tkinter as tk
        from tkinter import scrolledtext, ttk
    except ImportError:  # pragma: no cover - only reachable on no-Tk boxes
        print(
            "The GUI needs Tkinter, which is not installed here.\n"
            "  Debian/Ubuntu:  sudo apt install python3-tk\n"
            "  macOS (brew):   brew install python-tk\n"
            "Until then, use:  shaggoth chat   (terminal REPL)\n"
            "or:               shaggoth serve  (web dashboard)"
        )
        return 1

    from .core import GUIController

    controller = GUIController(engine, supervisor=supervisor)

    root = tk.Tk()
    root.title(f"{controller.bot_name} — desktop")
    root.geometry("640x620" if supervisor is not None else "640x560")
    root.minsize(480, 420)

    chat = scrolledtext.ScrolledText(root, state="disabled", wrap="word", font=("monospace", 11))
    chat.pack(side="top", fill="both", expand=True, padx=8, pady=8)

    # Training panel. Only built when there is a crew to report on, so a
    # local-only install is not given an empty box to wonder about.
    training = None
    if supervisor is not None:
        frame = ttk.LabelFrame(root, text="Training")
        frame.pack(side="top", fill="x", padx=8, pady=(0, 8))
        training = tk.Label(
            frame, text="", anchor="w", justify="left", font=("monospace", 9)
        )
        training.pack(fill="x", padx=6, pady=4)

    mode_var = tk.StringVar(value="no_drift")

    def _render(turn) -> None:
        chat.configure(state="normal")
        chat.insert("end", f"\nYou > {turn.user}\n")
        tag = f"[{turn.source}]" if turn.source != "pattern" else ""
        if turn.mode != "no_drift":
            tag = f"[{turn.source} · {turn.mode}]"
        chat.insert("end", f"{controller.bot_name}{'> ' if tag else ''}{tag} {turn.text}\n")
        if turn.blocked:
            chat.insert("end", "(blocked by a guardrail)\n")
        if turn.entries_used:
            chat.insert("end", f"      from: {', '.join(turn.entries_used)}\n")
        chat.see("end")
        chat.configure(state="disabled")

    def _send(_event=None) -> None:
        text = entry.get().strip()
        if not text:
            return
        entry.delete(0, "end")
        try:
            turn = controller.send(text, mode=mode_var.get())
        except Exception as exc:  # noqa: BLE001 — keep the window alive
            _render_note(f"(error: {exc})")
            return
        _render(turn)

    def _reset() -> None:
        controller.reset()
        chat.configure(state="normal")
        chat.delete("1.0", "end")
        chat.configure(state="disabled")
        _render_note(controller.greeting())

    def _render_note(text: str) -> None:
        chat.configure(state="normal")
        chat.insert("end", f"\n{controller.bot_name} > {text}\n")
        chat.see("end")
        chat.configure(state="disabled")

    bar = ttk.Frame(root)
    bar.pack(side="bottom", fill="x", padx=8, pady=(0, 4))
    ttk.Label(bar, text="Mode:").pack(side="left")
    ttk.Combobox(
        bar,
        textvariable=mode_var,
        values=("no_drift", "drift"),
        state="readonly",
        width=12,
    ).pack(side="left", padx=(4, 12))
    ttk.Button(bar, text="New conversation", command=_reset).pack(side="left")

    entry = tk.Entry(root, font=("monospace", 12))
    entry.pack(side="bottom", fill="x", padx=8, pady=(0, 8))
    entry.bind("<Return>", _send)
    ttk.Button(root, text="Send", command=_send).pack(side="bottom", pady=(0, 8))

    status = tk.Label(root, text="", anchor="w", relief="sunken")
    status.pack(side="bottom", fill="x")

    def _refresh_status() -> None:
        s = controller.status()
        model = f"{s['model']} ({s['provider']})" if s["provider"] else s["model"]
        status.config(
            text=(
                f"{s['bot_name']} · model {model} · {s['knowledge_entries']} knowledge entries"
                f" · {s['turns']} turns"
            )
        )
        if training is not None:
            training.config(text="\n".join(controller.agent_lines()))
        root.after(2000, _refresh_status)

    _render_note(controller.greeting())
    _refresh_status()
    entry.focus_set()
    root.mainloop()
    return 0
