"""
Настройки и константы для постинга статей.
"""
# Config
from config import POSTGRES_DSN

# Константы
MEDIUM_NEW_STORY_URL = "https://medium.com/new-story"
QUORA_URL = "https://www.quora.com/"
ADS_POWER_API_URL = "http://local.adspower.net:50325"
ADS_POWER_API_KEY = "856007acdf241361915ed26a00a6d70b"

# Маппинг profile_id -> profile_no для удобства в логах
# Формат: {profile_id: profile_no}
PROFILE_MAPPING = {
    "kqnfhbe": 70,
    "kqnfhbi": 74,
    "kqnfhbo": 80,
    "kqnfhbx": 89,
    "kqnfhby": 90,
    "kqnfhc0": 91,
    "kqnfhc1": 92,
    "kqnfhc2": 93,
    "k107wk78": 125,
    "k107wyp0": 126,
}

# Последовательная нумерация профилей от 1 до 10
# Формат: {profile_no: sequential_no}
PROFILE_SEQUENTIAL_MAPPING = {
    70: 1,
    74: 2,
    80: 3,
    89: 4,
    90: 5,
    91: 6,
    92: 7,
    93: 8,
    125: 9,
    126: 10,
}

# ID профилей Ads Power (циклический перебор) - используем profile_id для API
PROFILE_IDS = list(PROFILE_MAPPING.keys())


def get_profile_no(profile_id: str) -> int:
    """Получить profile_no по profile_id."""
    return PROFILE_MAPPING.get(profile_id, 0)


def get_profile_id(profile_no: int):
    """Получить profile_id по profile_no."""
    from typing import Optional
    for pid, pno in PROFILE_MAPPING.items():
        if pno == profile_no:
            return pid
    return None


def get_sequential_no(profile_no: int):
    """Получить sequential_no по profile_no."""
    from typing import Optional
    return PROFILE_SEQUENTIAL_MAPPING.get(profile_no)


def get_profile_id_by_sequential_no(sequential_no: int):
    """Получить profile_id по sequential_no."""
    from typing import Optional
    for profile_no, seq_no in PROFILE_SEQUENTIAL_MAPPING.items():
        if seq_no == sequential_no:
            profile_id = get_profile_id(profile_no)
            if profile_id:
                return profile_id
    return None


def get_profile_no_by_sequential_no(sequential_no: int):
    """Получить profile_no по sequential_no."""
    from typing import Optional
    for profile_no, seq_no in PROFILE_SEQUENTIAL_MAPPING.items():
        if seq_no == sequential_no:
            return profile_no
    return None

