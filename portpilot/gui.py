"""Window: Ports (filter, open in browser, details, stop), WSL, Docker and the hosts file."""
from __future__ import annotations

import queue
import sys
import threading
import webbrowser

from . import __version__, system


def main() -> int:
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.title(f"PortPilot {__version__}")
    root.geometry("1000x620")
    messages: queue.Queue = queue.Queue()
    state = {"rows": {}}
    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=10, pady=10)

    def background(task, kind) -> None:
        def work():
            try:
                messages.put((kind, task()))
            except Exception as exc:  # shown in the status bar
                messages.put(("error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    # --- Ports ----------------------------------------------------------------------
    ports_tab = ttk.Frame(notebook, padding=8)
    notebook.add(ports_tab, text="Ports")
    bar = ttk.Frame(ports_tab)
    bar.pack(fill="x")
    query = tk.StringVar()
    show_all = tk.BooleanVar(value=False)
    ttk.Label(bar, text="Filter").pack(side="left")
    ttk.Entry(bar, textvariable=query, width=24).pack(side="left", padx=6)
    ttk.Checkbutton(bar, text="Show Windows' dynamic ports", variable=show_all,
                    command=lambda: fill_ports(state.get("listeners", []))).pack(side="left")
    columns = ("port", "scope", "pid", "process", "what")
    tree = ttk.Treeview(ports_tab, columns=columns, show="headings")
    for column, title, width in (("port", "Port", 70), ("scope", "Reachable from", 110), ("pid", "PID", 70),
                                 ("process", "Program", 260), ("what", "Usually", 260)):
        tree.heading(column, text=title)
        tree.column(column, width=width, anchor="w")
    tree.pack(fill="both", expand=True, pady=8)
    detail = ttk.Label(ports_tab, text="Select a row to see its full command line.", anchor="w")
    detail.pack(fill="x")
    actions = ttk.Frame(ports_tab)
    actions.pack(fill="x", pady=(6, 0))

    def fill_ports(found) -> None:
        state["listeners"] = found
        tree.delete(*tree.get_children())
        state["rows"] = {}
        needle = query.get().strip().lower()
        for index, item in enumerate(found):
            if not show_all.get() and item.port >= 49152:
                continue
            if needle and needle not in f"{item.port} {item.process} {item.label}".lower():
                continue
            iid = str(index)
            state["rows"][iid] = item
            tree.insert("", "end", iid=iid, values=(item.port, "this PC only" if item.local_only else "the network",
                                                     item.pid, item.process, item.label))

    def selected():
        focus = tree.focus()
        return state["rows"].get(focus)

    def on_select(_event=None) -> None:
        item = selected()
        if item:
            detail.configure(text="Looking up…")
            background(lambda: (item.pid, system.command_line(item.pid)), "detail")

    def open_browser() -> None:
        item = selected()
        if item:
            webbrowser.open(item.browser_url)

    def stop_selected(force: bool = False) -> None:
        item = selected()
        if not item:
            return
        refusal = system.stop_refusal(item)
        if refusal:
            messagebox.showwarning("PortPilot", f"PortPilot won't stop {item.process}: {refusal}.")
            return
        verb = "Force-stop" if force else "Stop"
        if not messagebox.askyesno("PortPilot", f"{verb} {item.process} (PID {item.pid}) on port {item.port}?\n\n"
                                                "Unsaved work in that program may be lost.", icon="warning"):
            return
        try:
            messagebox.showinfo("PortPilot", system.stop(item, force=force))
        except (PermissionError, RuntimeError) as exc:
            messagebox.showerror("PortPilot", str(exc))
        refresh()

    def refresh() -> None:
        background(system.listeners, "ports")

    tree.bind("<<TreeviewSelect>>", on_select)
    query.trace_add("write", lambda *_: fill_ports(state.get("listeners", [])))
    ttk.Button(actions, text="Refresh", command=refresh).pack(side="left")
    ttk.Button(actions, text="Open in browser", command=open_browser).pack(side="left", padx=6)
    ttk.Button(actions, text="Stop program…", command=stop_selected).pack(side="left")
    ttk.Button(actions, text="Force stop…", command=lambda: stop_selected(True)).pack(side="left", padx=6)
    ttk.Button(actions, text="Copy a free port",
               command=lambda: (root.clipboard_clear(), root.clipboard_append(str(system.free_port())))).pack(side="right")

    # --- WSL, Docker, hosts -------------------------------------------------------------
    other = ttk.Frame(notebook, padding=8)
    notebook.add(other, text="WSL, Docker, hosts")
    info = tk.Text(other, wrap="word", font=("Consolas", 10))
    info.pack(fill="both", expand=True)
    other_bar = ttk.Frame(other)
    other_bar.pack(fill="x", pady=(6, 0))

    def load_other():
        lines = ["WSL distributions"]
        distros = system.wsl_distros()
        lines += [f"  {'*' if d.default else ' '} {d.name:<22} {d.state:<10} WSL {d.version}" for d in distros] or ["  none"]
        containers = system.docker_containers()
        lines += ["", "Docker containers"]
        if containers is None:
            lines.append("  Docker isn't installed or isn't running.")
        else:
            lines += [f"  {c['name']:<26} {c['status']:<20} {c['ports']}" for c in containers] or ["  none running"]
        lines += ["", f"hosts file ({system.HOSTS})"]
        lines += [f"  {a:<16} {' '.join(n)}" for a, n, _ in system.hosts_entries()] or ["  no active entries"]
        return "\n".join(lines)

    ttk.Button(other_bar, text="Refresh", command=lambda: background(load_other, "other")).pack(side="left")
    ttk.Button(other_bar, text="Shut down WSL",
               command=lambda: messagebox.askyesno("PortPilot", "Shut down every WSL distro?")
               and background(lambda: system.wsl_action("shutdown"), "done")).pack(side="left", padx=6)
    ttk.Button(other_bar, text="Edit hosts file (admin)", command=system.edit_hosts_as_admin).pack(side="left")
    status = ttk.Label(root, text="", anchor="w")
    status.pack(fill="x", padx=12, pady=(0, 8))

    def pump() -> None:
        while True:
            try:
                kind, payload = messages.get_nowait()
            except queue.Empty:
                break
            if kind == "ports":
                fill_ports(payload)
                status.configure(text=f"{len(payload)} listening TCP ports.")
            elif kind == "detail":
                pid, text = payload
                item = selected()
                if item and item.pid == pid:
                    detail.configure(text=text[:220] or "(no command line available)")
            elif kind == "other":
                info.delete("1.0", "end")
                info.insert("1.0", payload)
            elif kind == "done":
                status.configure(text=str(payload)[:150])
            elif kind == "error":
                status.configure(text=payload[:150])
        root.after(150, pump)

    refresh()
    background(load_other, "other")
    root.after(150, pump)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
