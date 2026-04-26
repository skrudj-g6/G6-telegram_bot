import re

def is_valid_id(player_id: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{4}", player_id))