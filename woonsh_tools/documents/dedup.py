"""
Дедупликация документов: SHA-256 идентификация, консолидация профилей.
Из X-File document_dedup.py — адаптировано для Woonsh Tools.
"""

import copy
import datetime
import hashlib
from pathlib import Path
import shutil
import uuid
import zipfile


def normalized(value):
    return ' '.join(value.casefold().split())


def profile_identity(name, company):
    return 'doc-' + hashlib.sha256(
        (normalized(name) + '\n' + normalized(company)).encode('utf-8')
    ).hexdigest()


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def within(path, root):
    resolved = Path(path).resolve()
    root = Path(root).resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise ValueError('Folder outside archive')
    return resolved


def consolidate(data, registry, docs_root, save_fn=None):
    """Копирует/проверяет, коммитит метаданные, удаляет дубликаты."""
    if data.get('identity_version') == 2:
        return data, {'merged': 0, 'removed_folders': 0}

    docs_root = Path(docs_root)
    profile_root = docs_root / 'profiles'
    groups = {}
    key_map = {}

    for old_key, owner in data['profiles'].items():
        key = profile_identity(owner['name'], owner.get('company', ''))
        key_map[old_key] = key
        groups.setdefault(key, []).append((old_key, owner))

    updated = copy.deepcopy(data)
    updated['profiles'] = {}
    folder_groups = []
    merged = 0

    for key, group in groups.items():
        folders = []
        for _, owner in group:
            if owner.get('folder'):
                folder = within(owner['folder'], profile_root)
                if folder not in folders:
                    folders.append(folder)
        folders.sort(key=lambda f: (len(f.name), f.name.casefold()))
        chosen = folders[0] if folders else None
        if chosen:
            folder_groups.append((chosen, folders))

        owner = copy.deepcopy(group[0][1])
        owner['docs'] = []
        if chosen:
            owner['folder'] = str(chosen)

        seen = {}
        for _, other in group:
            for original in other.get('docs', []):
                document = copy.deepcopy(original)
                fingerprint = document.get('sha256') or document['id']
                if fingerprint not in seen:
                    seen[fingerprint] = document
                    owner['docs'].append(document)
                else:
                    target = seen[fingerprint]
                    if document.get('checked') and not target.get('checked'):
                        target['fields'] = document.get('fields', {})
                        target['checked'] = True
                    for field, value in document.get('fields', {}).items():
                        if value and not target.setdefault('fields', {}).get(field):
                            target['fields'][field] = value
                    target.setdefault('profile_paths', {}).update(
                        document.get('profile_paths', {}))

        updated['profiles'][key] = owner
        merged += len(group) - 1

    # Бэкап перед консолидацией
    backup = None
    if Path(registry).exists():
        backup = (docs_root.parent / 'backups'
                  / ('documents_merge_'
                     + datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                     + '_' + uuid.uuid4().hex[:6]))
        backup.mkdir(parents=True)
        shutil.copy2(registry, backup / 'documents_registry.dpapi')
        with zipfile.ZipFile(backup / 'profile_folders.zip', 'w',
                             zipfile.ZIP_DEFLATED) as archive:
            recorded = set()
            for _, folders in folder_groups:
                if len(folders) < 2:
                    continue
                for folder in folders:
                    if folder in recorded or not folder.exists():
                        continue
                    recorded.add(folder)
                    for path in folder.rglob('*'):
                        within(path, profile_root)
                        if path.is_file():
                            archive.write(path, str(path.relative_to(profile_root)))

    # Копирование и верификация
    path_map = {}
    verified = []
    for target, folders in folder_groups:
        for folder in folders:
            if folder == target or not folder.exists():
                continue
            for source in folder.rglob('*'):
                if not source.is_file():
                    continue
                within(source, profile_root)
                dest = target / source.relative_to(folder)
                within(dest, profile_root)
                dest.parent.mkdir(parents=True, exist_ok=True)
                fingerprint = file_hash(source)
                number = 2
                while dest.exists() and file_hash(dest) != fingerprint:
                    dest = dest.with_name(
                        '%s (%d)%s' % (source.stem, number, source.suffix))
                    number += 1
                if not dest.exists():
                    temp = dest.with_suffix(dest.suffix + '.merge-tmp')
                    shutil.copy2(source, temp)
                    temp.replace(dest)
                if file_hash(dest) != fingerprint:
                    raise OSError('Document copy verification failed')
                path_map[str(source)] = str(dest)
                verified.append((source, dest, fingerprint))

    # Обновление путей
    for owner in list(updated['profiles'].values()) + list(
            updated['companies'].values()):
        for document in owner.get('docs', []):
            document['path'] = path_map.get(document['path'], document['path'])
            links = {}
            for key, path in document.get('profile_paths', {}).items():
                key = key_map.get(key, key)
                links[key] = path_map.get(path, path)
            document['profile_paths'] = links

    updated['identity_version'] = 2

    if save_fn:
        save_fn(Path(registry), updated)

    # Удаление верифицированных оригиналов
    for source, dest, fingerprint in verified:
        within(source, profile_root)
        if (backup and source.exists()
                and file_hash(source) == fingerprint
                and file_hash(dest) == fingerprint):
            source.unlink()

    removed = 0
    for target, folders in folder_groups:
        for folder in folders:
            if folder == target or not folder.exists():
                continue
            within(folder, profile_root)
            for child in sorted(
                    (p for p in folder.rglob('*') if p.is_dir()),
                    key=lambda p: len(p.parts), reverse=True):
                within(child, profile_root)
                try:
                    child.rmdir()
                except OSError:
                    pass
            try:
                folder.rmdir()
                removed += 1
            except OSError:
                pass

    return updated, {'merged': merged, 'removed_folders': removed,
                     'backup': str(backup) if backup else None}
