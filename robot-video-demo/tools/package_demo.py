"""Create a source ZIP without local environments, binaries or runtime logs."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".runtime", ".venv", "__pycache__", ".pytest_cache", "node_modules", "artifacts", ".git"}
SOURCE_DIRS = {"web", "docs", "tests", "tools", ".vscode"}

if __name__ == "__main__":
    target = ROOT.parent / "robot-camera-complete.zip"
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for file in sorted(ROOT.rglob("*")):
            relative = file.relative_to(ROOT)
            if not file.is_file() or EXCLUDED.intersection(relative.parts):
                continue
            if len(relative.parts) > 1 and relative.parts[0] not in SOURCE_DIRS:
                continue
            if file.name in (".env", "cameras.local.json") or file.suffix in (".zip", ".log", ".pyc"):
                continue
            # Distribute a known credential-free four-channel default, even if
            # the developer's local cameras.json later contains device secrets.
            if relative.as_posix() == "cameras.json":
                archive.writestr(str(Path(ROOT.name) / relative), '''{
  "cameras": [
    {"id":"camera_1","name":"机器狗 · 前摄像头","source":"m20","camera":"front","url":""},
    {"id":"camera_2","name":"机器狗 · 后摄像头","source":"m20","camera":"back","url":""},
    {"id":"camera_3","name":"机械臂 · D435 彩色画面","source":"publisher"},
    {"id":"camera_4","name":"机器狗 · D455 彩色画面","source":"publisher"}
  ]
}
''')
            else:
                archive.write(file, Path(ROOT.name) / relative)
    print(target)
