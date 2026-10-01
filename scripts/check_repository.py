"""Dependency-free checks for this documentation/prototype repository."""
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
tracked = subprocess.check_output(
    ["git", "ls-files", "-z"], cwd=ROOT
).decode("utf-8").split("\0")
errors = []
for name in filter(None, tracked):
    path = ROOT / name
    parts = Path(name).parts
    if name.startswith("data/") or any(
        part in {"node_modules", ".venv", "__pycache__", ".aws"} for part in parts
    ):
        errors.append(f"Local-only path is tracked: {name}")
    if path.name == ".env" or (
        path.name.startswith(".env.") and not path.name.endswith(".example")
    ):
        errors.append(f"Environment file is tracked: {name}")
    if not path.is_file():
        errors.append(f"Tracked file is missing: {name}")
        continue
    if path.stat().st_size > 10 * 1024 * 1024:
        errors.append(f"File exceeds repository's 10 MiB review threshold: {name}")
    if path.suffix != ".md":
        continue
    content = path.read_text(encoding="utf-8")
    # Validate relative Markdown links; ignore code examples and external URLs.
    prose = re.sub(r"```.*?```", "", content, flags=re.S)
    for target in re.findall(r"\]\(([^)]+)\)", prose):
        target = target.strip().strip("<>")
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#"):
            continue
        relative = unquote(target.split("#", 1)[0])
        if relative and not (path.parent / relative).exists():
            errors.append(f"Broken relative link in {name}: {target}")

if errors:
    raise SystemExit("\n".join(errors))
print("PASS: tracked-file policy and relative Markdown links")
