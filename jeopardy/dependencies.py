from fastapi import Request

from jeopardy.services.buzzer import BuzzerService
from jeopardy.services.game_manager import GameManager
from jeopardy.services.scoring import ScoringService


def get_game_manager(request: Request) -> GameManager:
    return request.app.state.game_manager


def get_buzzer(request: Request) -> BuzzerService:
    return request.app.state.buzzer


def get_scoring(request: Request) -> ScoringService:
    return request.app.state.scoring
