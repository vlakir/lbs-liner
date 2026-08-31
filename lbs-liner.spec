# Спецификация PyInstaller: два исполняемых файла из одного прогона.
#   dist/lbs-liner      — консольный CLI (пакетный режим, параметры).
#   dist/lbs-liner-gui  — окно без консоли (двойной клик).
# Сборка: uv run pyinstaller lbs-liner.spec

cli_a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    excludes=['tkinter'],
    noarchive=False,
)

gui_a = Analysis(
    ['src/gui_main.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    excludes=[],
    noarchive=False,
)

cli_pyz = PYZ(cli_a.pure)
gui_pyz = PYZ(gui_a.pure)

cli_exe = EXE(
    cli_pyz,
    cli_a.scripts,
    cli_a.binaries,
    cli_a.datas,
    [],
    name='lbs-liner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

gui_exe = EXE(
    gui_pyz,
    gui_a.scripts,
    gui_a.binaries,
    gui_a.datas,
    [],
    name='lbs-liner-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
