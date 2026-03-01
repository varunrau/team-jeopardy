from enum import Enum
from typing import Optional
import uuid

from pydantic import BaseModel, Field


class GameStatus(str, Enum):
    LOBBY = "lobby"
    IN_PROGRESS = "in_progress"
    FINAL_JEOPARDY = "final_jeopardy"
    FINISHED = "finished"


class Clue(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    answer: str
    clue_text: str
    clue_image_url: Optional[str] = None
    category: str
    dollar_value: int
    is_daily_double: bool = False
    is_answered: bool = False


class Team(BaseModel):
    team_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    team_token: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    score: int = 0
    final_wager: Optional[int] = None
    final_answer: Optional[str] = None


class GameState(BaseModel):
    game_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: GameStatus = GameStatus.LOBBY
    teams: dict[str, Team] = {}
    board: dict[str, list[Clue]] = {}
    current_clue: Optional[Clue] = None
    buzz_order: list[str] = []
    buzz_window_open: bool = False
    current_answering_team: Optional[str] = None
    daily_double_clue_id: Optional[str] = None
    # Track teams excluded from current buzz window (answered incorrectly)
    buzz_excluded_teams: list[str] = []
