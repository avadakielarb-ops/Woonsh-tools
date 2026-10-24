"""
Google Drive upload panel — PDF↔company matching, rclone upload, links.
From X-File x-file.pyw drive sections — adapted for Woonsh Tools.
"""
import json
import os
import re
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from concurrent.futures import ThreadPoolExecutor

from woonsh_tools.core.theme import make_card


class DrivePanel(ttk.Frame):
    """Google Drive upload tab with PDF matching and rclone integration."""

    def __init__(self, parent, app):
        super().__init__(parent, padding=12)
        self.app = app
        self.working = False
        self.companies = []
        self.pdf_files = []
        self.rows = {}
        self.links = {}

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Папка с PDF:").grid(
            row=0, column=0, sticky="w")
        self.var_folder = tk.StringVar()
        ttk.Entry(top, textvariable=self.var_folder).grid(
            row=0, column=1, sticky="ew", padx=8)
        ttk.Button(top, text="Обзор…", command=self._browse_folder).grid(
            row=0, column=2)

        ttk.Label(top, text="Google Drive ID:").grid(
            row=1, column=0, sticky="w", pady=(8, 0))
        self.var_drive = tk.StringVar()
        ttk.Entry(top, textvariable=self.var_drive).grid(
            row=1, column=1, sticky="ew", padx=8, pady=(8, 0))

        buttons = ttk.Frame(self)
        buttons.grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Button(buttons, text="Проверить Drive",
                   command=self._check_drive).pack(side="left")
        ttk.Button(buttons, text="Загрузить", style="Accent.TButton",
                   command=self._upload).pack(side="left", padx=8)
        ttk.Button(buttons, text="Скачать rclone",
                   command=self._get_rclone).pack(side="left")

        self.status_var = tk.StringVar(value="Готово")
        ttk.Label(self, textvariable=self.status_var,
                  wraplength=700).grid(
            row=3, column=0, sticky="w", pady=8)

        tree_frame = ttk.Frame(self)
        tree_frame.grid(row=2, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("file", "status", "link"),
            show="headings", selectmode="browse")
        self.tree.heading("file", text="PDF файл")
        self.tree.heading("status", text="Статус")
        self.tree.heading("link", text="Ссылка Drive")
        self.tree.column("file", width=300)
        self.tree.column("status", width=120)
        self.tree.column("link", width=400)
        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

    def _browse_folder(self):
        folder = filedialog.askdirectory(parent=self)
        if folder:
            self.var_folder.set(folder)

    def _find_rclone(self):
        from woonsh_tools.drive.rclone import find_rclone
        return find_rclone(self.app.cfg.get("rclone", ""))

    def _check_drive(self):
        exe = self._find_rclone()
        if not exe:
            self.status_var.set("rclone не найден. Нажмите «Скачать rclone».")
            return
        from woonsh_tools.drive.rclone import drive_folder_id, check_drive
        fid = drive_folder_id(self.var_drive.get())
        self.status_var.set("Проверяю доступ…")

        def worker():
            ok, msg = check_drive(exe, fid)
            self.app.emit("status", msg)
        threading.Thread(target=worker, daemon=True).start()

    def _get_rclone(self):
        self.status_var.set("Скачиваю rclone…")

        def worker():
            try:
                from woonsh_tools.drive.rclone import download_rclone
                tools_dir = os.path.join(self.app.app_data_dir, "rclone")
                os.makedirs(tools_dir, exist_ok=True)
                path = download_rclone(tools_dir)
                self.app.cfg["rclone"] = path
                self.app.emit("status", "rclone готов: " + path)
            except Exception as exc:
                self.app.emit("status", "Ошибка скачивания rclone: " + str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _upload(self):
        exe = self._find_rclone()
        if not exe:
            self.status_var.set("rclone не найден.")
            return
        folder = self.var_folder.get().strip()
        if not folder or not os.path.isdir(folder):
            self.status_var.set("Выберите папку с PDF.")
            return
        from woonsh_tools.drive.rclone import (
            drive_folder_id, upload_file, list_drive_files)
        fid = drive_folder_id(self.var_drive.get())
        if not fid:
            self.status_var.set("Укажите ID папки Google Drive.")
            return

        pdfs = [f for f in os.listdir(folder)
                if f.lower().endswith(".pdf")]
        if not pdfs:
            self.status_var.set("В папке нет PDF файлов.")
            return

        if not messagebox.askyesno(
                "Загрузить?",
                f"Загрузить {len(pdfs)} PDF на Google Drive?",
                parent=self):
            return

        self.working = True
        self.status_var.set("Загружаю…")

        def worker():
            done, errors = [], []
            lock = threading.Lock()
            counter = {"n": 0}

            def one(pdf):
                src = os.path.join(folder, pdf)
                ok, err = upload_file(exe, src, pdf, fid)
                with lock:
                    counter["n"] += 1
                if ok:
                    done.append(pdf)
                else:
                    errors.append((pdf, err))
                self.app.emit(
                    "status", f"Загружено {counter['n']} из {len(pdfs)}")

            with ThreadPoolExecutor(max_workers=3) as pool:
                list(pool.map(one, pdfs))

            files = list_drive_files(exe, fid)
            ids = {row["Name"]: row.get("ID", "") for row in files}

            def update_tree():
                self.tree.delete(*self.tree.get_children())
                for pdf in pdfs:
                    fid_file = ids.get(pdf, "")
                    link = (f"https://drive.google.com/file/d/{fid_file}/view"
                            if fid_file else "")
                    status = "✓" if pdf in done else "✗"
                    self.tree.insert("", "end",
                                     values=(pdf, status, link))
            self.after(0, update_tree)
            self.working = False
            msg = f"Загружено: {len(done)}"
            if errors:
                msg += f", ошибок: {len(errors)}"
            self.app.emit("status", msg)

        threading.Thread(target=worker, daemon=True).start()
