# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[("assets/app_icon.png", "assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Gestion Serveurs Minecraft",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Gestion Serveurs Minecraft",
)
app = BUNDLE(
    coll,
    name="Gestion Serveurs Minecraft.app",
    icon="assets/AppIcon.icns",
    bundle_identifier="local.gestionserveursminecraft.app",
    info_plist={
        "CFBundleName": "Gestion Serveurs Minecraft",
        "CFBundleDisplayName": "Gestion Serveurs Minecraft",
        "CFBundleShortVersionString": "1.0.3",
        "CFBundleVersion": "1.0.3",
        "NSHighResolutionCapable": "True",
        "NSRequiresAquaSystemAppearance": "False",
    },
)
