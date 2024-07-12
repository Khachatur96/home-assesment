import os


MAX_RETRY_LIMIT = 100

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STATES = [
    "idle",
    "listening",
    "processing",
    "process_interrupted",
    "responding"
]

MOODS = [
    "happy",
    "neutral",
    "amused",
    "sorry",
    "sad"
]

LOG_LEVELS = [
    "info",
    "debug",
    "warning",
    "error",
    "fatal"
]
