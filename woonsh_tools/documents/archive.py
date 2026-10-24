"""
Архивы документов: чтение ZIP/RAR, path traversal protection, ревью пар.
Слияние X-File document_archive.py + document_archive_review.py.
"""

import hashlib
import os
from pathlib import Path, PurePosixPath
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
import zipfile

LIMIT = 20 * 1024 * 1024
EXTENSIONS = {'.jpg', '.jpeg', '.png', '.pdf', '.tif', '.tiff', '.bmp'}


def safe_name(name):
    name = name.replace('\\', '/')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or ':' in name or '\x00' in name:
        raise ValueError('Unsafe archive entry')
    return name


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_pairs(archives, target, classifier=None):
    """Чтение пар front/back из ZIP/RAR архивов."""
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    groups = []
    skipped = 0
    total = 0

    for archive_index, archive in enumerate(archives):
        archive = Path(archive)
        z = None

        if archive.suffix.lower() == '.zip':
            z = zipfile.ZipFile(archive)
            names = [info.filename for info in z.infolist() if not info.is_dir()]
        elif archive.suffix.lower() == '.rar':
            tar = Path(os.environ.get('SystemRoot', r'C:\Windows')) / \
                  'System32/tar.exe'
            process = subprocess.run(
                [str(tar), '-tf', str(archive)],
                stdin=subprocess.DEVNULL, capture_output=True, timeout=60,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000))
            if process.returncode:
                raise ValueError('Cannot read archive')
            try:
                names = process.stdout.decode('utf-8').splitlines()
            except UnicodeDecodeError:
                names = process.stdout.decode('cp1251').splitlines()
        else:
            raise ValueError('Only ZIP/RAR supported')

        try:
            if len(names) > 2000 or len(set(names)) != len(names):
                raise ValueError('Archive entry limit or duplicate names')

            folders = {}
            for raw in names:
                member = PurePosixPath(safe_name(raw))
                if member.suffix.lower() in EXTENSIONS:
                    folders.setdefault(str(member.parent), []).append(raw)

            def extract(member, number):
                nonlocal total
                if z:
                    info = z.getinfo(member)
                    if info.file_size > LIMIT:
                        raise ValueError('Document too large')
                    with z.open(info) as stream:
                        data = stream.read(LIMIT + 1)
                else:
                    proc = subprocess.Popen(
                        [str(tar), '-xOf', str(archive), '--', member],
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW',
                                              0x08000000))
                    try:
                        data = proc.stdout.read(LIMIT + 1)
                        if len(data) > LIMIT:
                            proc.kill()
                            raise ValueError('Document too large')
                        if proc.wait(timeout=60):
                            raise ValueError('Cannot extract document')
                    finally:
                        if proc.poll() is None:
                            proc.kill()
                            proc.wait()
                        proc.stdout.close()

                total += len(data)
                if not data or len(data) > LIMIT or total > 300 * 1024 * 1024:
                    raise ValueError('Document size limit')
                path = target / ('%d_%d_%d%s' % (
                    archive_index, group_index, number,
                    PurePosixPath(member.replace('\\', '/')).suffix.lower()))
                path.write_bytes(data)
                return str(path)

            for group_index, (folder, members) in enumerate(
                    sorted(folders.items())):
                conventional = {}
                for raw in members:
                    stem = PurePosixPath(safe_name(raw)).stem.casefold().strip()
                    side = {'фронт': 'front', 'фронд': 'front',
                            'бэк': 'back', 'бек': 'back'}.get(stem, stem)
                    if side in ('front', 'back'):
                        if side in conventional:
                            raise ValueError('Ambiguous named side')
                        conventional[side] = raw

                result = {'label': archive.name + ' / ' + folder}

                if set(conventional) == {'front', 'back'}:
                    for number, (side, raw) in enumerate(conventional.items()):
                        result[side] = extract(raw, number)
                elif classifier:
                    if len(members) > 30:
                        raise ValueError('Too many candidates in one folder')
                    candidates = []
                    for number, raw in enumerate(members):
                        path = extract(raw, number)
                        try:
                            classification = classifier(path)
                        except Exception:
                            classification = {'side': 'unknown', 'score': 0,
                                              'reason': 'Не прочитан'}
                        candidates.append(dict(
                            classification, path=path,
                            name=PurePosixPath(safe_name(raw)).name))
                    result['candidates'] = candidates
                    result['needs_review'] = True
                    for side in ('front', 'back'):
                        ranked = sorted(
                            (c for c in candidates if c.get('side') == side),
                            key=lambda c: c.get('score', 0), reverse=True)
                        if (ranked and ranked[0].get('score', 0) >= 3
                                and (len(ranked) == 1
                                     or ranked[0]['score'] > ranked[1]['score'])):
                            result[side] = ranked[0]['path']
                else:
                    skipped += 1
                    continue

                if result.get('front') and result.get('back'):
                    result['front_sha'] = sha(result['front'])
                    result['back_sha'] = sha(result['back'])
                    result['id'] = hashlib.sha256(
                        (result['front_sha'] + '\n' + result['back_sha']
                         ).encode()).hexdigest()
                groups.append(result)
        finally:
            if z:
                z.close()

    return groups, skipped


# ---------------------------------------------------------------------------
# Диалог ревью пар (front/back)
# ---------------------------------------------------------------------------

class ArchiveReview(tk.Toplevel):
    """Диалог выбора front/back для каждой папки архива."""

    def __init__(self, parent, groups):
        super().__init__(parent)
        self.title('Отбор документов из архива')
        self.geometry('1100x650')
        self.transient(parent.winfo_toplevel())
        self.result = None
        self.groups = groups
        self.choices = []

        ttk.Label(
            self,
            text='Проверьте фронт и бэк для каждой папки. '
                 'Только два выбранных файла попадут на склад; '
                 'остальные фотографии не сохраняются.',
            wraplength=1050).pack(anchor='w', padx=12, pady=12)

        from woonsh_tools.core.scroll import ScrollFields
        pane = ScrollFields(self)
        pane.pack(fill='both', expand=True, padx=12)
        pane.content.columnconfigure(1, weight=1)

        for index, group in enumerate(groups):
            start = index * 4
            ttk.Label(pane.content, text=group['label'],
                      style='H.TLabel').grid(
                row=start, column=0, columnspan=3,
                sticky='w', pady=(12, 5))

            candidates = group.get('candidates') or [
                {'path': group['front'], 'name': Path(group['front']).name,
                 'side': 'front', 'score': 99, 'reason': 'Имя front'},
                {'path': group['back'], 'name': Path(group['back']).name,
                 'side': 'back', 'score': 99, 'reason': 'Имя back'},
            ]

            labels = ['Пропустить'] + [
                '%s — %s' % (c['name'], c.get('reason', 'Проверьте'))
                for c in candidates]
            lookup = dict(zip(labels[1:], candidates))
            values = {}

            for offset, side, title in [(1, 'front', 'Фронт'),
                                         (2, 'back', 'Бэк')]:
                ttk.Label(pane.content, text=title).grid(
                    row=start + offset, column=0, sticky='w', padx=8)
                var = tk.StringVar(value='Пропустить')
                suggested = group.get(side)
                for label, candidate in lookup.items():
                    if candidate['path'] == suggested:
                        var.set(label)
                        break
                ttk.Combobox(
                    pane.content, textvariable=var, values=labels,
                    state='readonly', width=85).grid(
                    row=start + offset, column=1, sticky='we', padx=8, pady=4)

                def open_choice(v=var, l=lookup):
                    if v.get() in l:
                        os.startfile(l[v.get()]['path'])

                ttk.Button(pane.content, text='Открыть файл',
                           command=open_choice).grid(
                    row=start + offset, column=2, padx=8)
                values[side] = var

            self.choices.append((group, values, lookup))

        pane.bind_fields()

        bar = ttk.Frame(self)
        bar.pack(fill='x', padx=12, pady=12)
        ttk.Button(bar, text='Отмена', command=self.destroy).pack(side='right')
        ttk.Button(bar, text='Забрать только выбранные документы',
                   command=self.accept, style='Accent.TButton').pack(
            side='right', padx=8)
        self.grab_set()

    def accept(self):
        selected = []
        for group, values, lookup in self.choices:
            front = lookup.get(values['front'].get())
            back = lookup.get(values['back'].get())
            if not front and not back:
                continue
            if not front or not back or front['path'] == back['path']:
                messagebox.showerror(
                    'Проверьте пару',
                    'Выберите два разных файла — фронт и бэк — '
                    'либо пропустите обе стороны папки.',
                    parent=self)
                return
            result = {
                'label': group['label'],
                'front': front['path'],
                'back': back['path'],
            }
            result['front_sha'] = sha(result['front'])
            result['back_sha'] = sha(result['back'])
            result['id'] = hashlib.sha256(
                (result['front_sha'] + '\n' + result['back_sha']
                 ).encode()).hexdigest()
            selected.append(result)
        self.result = selected
        self.destroy()


def review_pairs(parent, groups):
    dialog = ArchiveReview(parent, groups)
    parent.wait_window(dialog)
    return dialog.result
