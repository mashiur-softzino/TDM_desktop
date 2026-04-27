# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

# Only the data files the app actually needs at runtime
datas = [
    ('SOFTZINO_LOGO.png', '.'),
    ('cal_icon.png', '.'),
]
# matplotlib needs its bundled fonts and style sheets to render charts
datas += collect_data_files('matplotlib', excludes=['**/__pycache__', '**/*.pyc'])
# qtawesome needs its MDI icon font files
datas += collect_data_files('qtawesome', excludes=['**/__pycache__', '**/*.pyc'])

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # Lazy-imported inside GradientCanvas.plot() — PyInstaller won't auto-detect
        'numpy',
        'scipy',
        'scipy.interpolate',
        'matplotlib.pyplot',
        'matplotlib.collections',
        # New module files added during refactor
        'ui_constants',
        'ui_widgets',
        'ui_sampling',
        'ui_patients',
        'app_logger',
        # PyNaCl for license token verification
        'nacl',
        'nacl.signing',
        'nacl.exceptions',
        # matplotlib QtAgg backend
        'matplotlib.backends.backend_qtagg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # GUI toolkits we don't use
        'tkinter', '_tkinter', 'tk', 'tcl',
        'wx', 'gtk', 'gi',
        # Unused matplotlib backends
        'matplotlib.backends.backend_pdf',
        'matplotlib.backends.backend_ps',
        'matplotlib.backends.backend_svg',
        'matplotlib.backends.backend_agg',
        'matplotlib.backends.backend_cairo',
        'matplotlib.backends.backend_gtk3',
        'matplotlib.backends.backend_gtk4',
        'matplotlib.backends.backend_tkagg',
        'matplotlib.backends.backend_wx',
        'matplotlib.backends.backend_wxagg',
        'matplotlib.backends._backend_tk',
        'matplotlib.tests',
        # Unused scipy submodules (we only use scipy.interpolate)
        'scipy.optimize',
        'scipy.stats',
        'scipy.signal',
        'scipy.io',
        'scipy.ndimage',
        'scipy.spatial',
        'scipy.linalg',
        'scipy.fft',
        'scipy.integrate',
        'scipy.sparse',
        'scipy.special',
        'scipy.cluster',
        'scipy.odr',
        # Test / dev modules
        'numpy.testing',
        'numpy.tests',
        'scipy.testing',
        'pytest', 'unittest',
        # Interactive / notebook tools not needed in production
        'IPython', 'jupyter', 'notebook',
        'pygments', 'docutils',
        # Other unused
        'xmlrpc', 'ftplib', 'imaplib', 'poplib', 'smtplib',
        'telnetlib', 'nntplib', 'antigravity',
        'multiprocessing.pool',
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AUC-Sampler',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['cal_icon.png'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='AUC-Sampler',
)
