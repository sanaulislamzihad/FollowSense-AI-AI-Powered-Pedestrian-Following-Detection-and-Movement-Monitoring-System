import os
import sys
import tempfile
from pathlib import Path

# Isolated data dir + SQLite DB for the test session (must happen before `app` is imported).
_tmp = Path(tempfile.mkdtemp(prefix="followsense_test_"))
os.environ.setdefault("FS_DATA_DIR", str(_tmp))
os.environ.setdefault("FS_DATABASE_URL", f"sqlite:///{(_tmp / 'test.db').as_posix()}")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
