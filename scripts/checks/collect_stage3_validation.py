"""Compatibility entry point for the current 13-concept Stage 3 evidence collector."""
from pathlib import Path
import sys

from collect_stage3_completion import main


if __name__ == "__main__":
    # Keep the historical command usable while collecting evidence from the
    # isolated acceptance artifact, never from a schema that has been removed.
    if "--tests-xml" not in sys.argv:
        root = Path(__file__).resolve().parents[2]
        sys.argv.extend(["--tests-xml",str(root / "artifacts/validation-db-tests.xml")])
    main()
