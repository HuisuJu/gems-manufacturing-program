# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project_root = Path.cwd()
src_dir = project_root / "src"
repo_root = project_root.parent
schema_dir = repo_root / "schema" / "json"

a = Analysis(
    [str(src_dir / "main.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=[
        (str(schema_dir), "schema/json"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="factory_tool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
