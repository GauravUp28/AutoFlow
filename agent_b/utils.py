from pathlib import Path
from datetime import datetime

def now_ts():
    return datetime.utcnow().isoformat() + "Z"

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def to_ms(seconds: float) -> int:
    return int(seconds * 1000)
