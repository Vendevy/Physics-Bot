import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "studybot.db"

MODEL = "claude-sonnet-4-6"
GRADER_MODEL = "claude-sonnet-4-6"
VALIDATE_MODEL = "claude-haiku-4-5"

GEN_PROVIDER = os.environ.get("GEN_PROVIDER", "anthropic")
GEN_MODEL = os.environ.get("GEN_MODEL", "claude-sonnet-4-6")

PAPERS_ROOT = ROOT
PHYSICS_SPEC = ROOT / "Physics Past Papers" / "171726-specification-accredited-a-level-gce-physics-a-h556.pdf"
PHYSICS_PAPERS_DIR = ROOT / "Physics Past Papers" / "Physics Question Paper"
PHYSICS_MS_DIR = ROOT / "Physics Past Papers" / "Physics Markscheme"

MATHS_SPEC = ROOT / "Mathematics Past Papers" / "a level maths specification.pdf"
MATHS_DIR = ROOT / "Mathematics Past Papers"

DAILY_NEW = 7
DAILY_RECALL = 3

# Error-boost tuning for pick_weakest_topics.
# Lower ERROR_BOOST_GRADE_MAX → only severe errors count (stricter).
# Raise ERROR_BOOST_PER_ERROR / ERROR_BOOST_CAP → booster more aggressive.
ERROR_BOOST_WINDOW_DAYS = 14
ERROR_BOOST_GRADE_MAX   = 2
ERROR_BOOST_PER_ERROR   = 0.1
ERROR_BOOST_CAP         = 0.3
