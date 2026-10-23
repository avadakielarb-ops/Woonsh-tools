# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('C:/Users/lesha/OneDrive/Desktop/X-File/company_directory/data/blacklist_industries.txt', 'company_directory/data'), ('C:/Users/lesha/OneDrive/Desktop/X-File/company_directory/data/brands.txt', 'company_directory/data'), ('C:/Users/lesha/OneDrive/Desktop/X-File/company_directory/data/not_a_website.txt', 'company_directory/data'), ('C:/Users/lesha/OneDrive/Desktop/X-File/ads_generator/app.py', 'ads_generator'), ('C:/Users/lesha/OneDrive/Desktop/X-File/ads_generator/index.html', 'ads_generator'), ('C:/Users/lesha/OneDrive/Desktop/X-File/ads_countries.json', '.'), ('C:/Users/lesha/OneDrive/Desktop/X-File/windows_ocr.ps1', '.'), ('C:/Users/lesha/OneDrive/Desktop/X-File/instrukciya.html', '.'), ('C:/Users/lesha/OneDrive/Desktop/X-File/build_release_work/release_source.json', '.')]
binaries = []
hiddenimports = ['company_directory.fallback', 'company_directory.statistics', 'company_directory.geos.registry', 'company_directory.search', 'company_directory.dnb', 'company_directory.browser', 'company_gemini', 'telegram_auth', 'rclone_download', 'visual_system', 'installation', 'user_profile', 'setup_wizard', 'ads_bridge', 'ads_native', 'ads_review', 'ads_validation', 'ads_selectors', 'app_update', 'company_search', 'document_archive', 'document_archive_review', 'document_classifier', 'document_dedup', 'document_fields', 'document_reader', 'document_stock', 'documents_panel', 'gemini_document', 'native_ocr', 'profile_panel', 'profile_scroll', 'profile_store', 'sidebar_navigation', 'ui_helpers']
tmp_ret = collect_all('playwright')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('telethon')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pymupdf')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:/Users/lesha/OneDrive/Desktop/X-File/x-file.pyw'],
    pathex=['C:/Users/lesha/OneDrive/Desktop/X-File'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MultiToolFarmer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
