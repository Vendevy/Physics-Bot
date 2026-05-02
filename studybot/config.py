from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "studybot.db"

MODEL = "claude-sonnet-4-6"
GRADER_MODEL = "claude-sonnet-4-6"
VALIDATE_MODEL = "claude-haiku-4-5"

PAPERS_ROOT = ROOT
PHYSICS_SPEC = ROOT / "Physics Past Papers" / "171726-specification-accredited-a-level-gce-physics-a-h556.pdf"
PHYSICS_PAPERS_DIR = ROOT / "Physics Past Papers" / "Physics Question Paper"
PHYSICS_MS_DIR = ROOT / "Physics Past Papers" / "Physics Markscheme"

MATHS_SPEC = ROOT / "Mathematics Past Papers" / "a level maths specification.pdf"
MATHS_DIR = ROOT / "Mathematics Past Papers"

DAILY_NEW = 7
DAILY_RECALL = 3
