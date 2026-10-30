import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./adaptive_math.db')
TIMEZONE = ZoneInfo(os.getenv('APP_TIMEZONE', 'Asia/Shanghai'))
PASS_MASTERY = float(os.getenv('PASS_MASTERY', '0.75'))
PASS_DISTINCT = int(os.getenv('PASS_DISTINCT', '5'))
WINDOW = int(os.getenv('MASTERY_WINDOW', '20'))
VERSION = 'rules-v1.0'
# An unfinished practice with no activity for this long stops guarding the assistant and accepts no more answers.
ASSESSMENT_TIMEOUT_MINUTES = int(os.getenv('ASSESSMENT_TIMEOUT_MINUTES', '120'))
if not 0 < PASS_MASTERY < 1 or not 1 <= PASS_DISTINCT <= WINDOW <= 100:
    raise ValueError('Invalid mastery/pass configuration')
