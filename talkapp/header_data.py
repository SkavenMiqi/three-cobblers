"""Chat activity dates for the original shared instrument header."""
from .storage import History


def get_active_dates():
    history = History()
    try:
        return {row[0]: True for row in history.db.execute('SELECT DISTINCT date(created) FROM messages')}
    finally:
        history.close()


def get_today_training_session():
    return None


def get_today_plan():
    return []
