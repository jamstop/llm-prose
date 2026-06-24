import sys
from pathlib import Path

# The tool is a single file one directory up; make `import deslop` work without
# any packaging or install (that's the whole point of the rewrite).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
