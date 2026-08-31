# Спецификация PyInstaller: единый lbs-liner — окно по двойному клику,
# консольный режим при запуске с аргументами (сборка без консольного окна).
# Сборка: uv run pyinstaller lbs-liner.spec

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
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
    name='lbs-liner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
