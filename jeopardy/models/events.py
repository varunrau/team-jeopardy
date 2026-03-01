from typing import Literal, Optional

from pydantic import BaseModel

from jeopardy.models.game import GameStatus


# --- Server -> Client Events ---


class BoardUpdate(BaseModel):
    type: Literal["BOARD_UPDATE"] = "BOARD_UPDATE"
    board: dict[str, list[dict]]
    scores: dict[str, int]
    team_names: dict[str, str]


class ClueSelected(BaseModel):
    type: Literal["CLUE_SELECTED"] = "CLUE_SELECTED"
    clue_text: str
    clue_image_url: Optional[str] = None
    category: str
    dollar_value: int
    is_daily_double: bool = False


class BuzzOpen(BaseModel):
    type: Literal["BUZZ_OPEN"] = "BUZZ_OPEN"


class BuzzLocked(BaseModel):
    type: Literal["BUZZ_LOCKED"] = "BUZZ_LOCKED"
    team_name: str


class BuzzWinner(BaseModel):
    type: Literal["BUZZ_WINNER"] = "BUZZ_WINNER"
    team_id: str
    team_name: str


class BuzzTimeout(BaseModel):
    type: Literal["BUZZ_TIMEOUT"] = "BUZZ_TIMEOUT"


class JudgeResult(BaseModel):
    type: Literal["JUDGE_RESULT"] = "JUDGE_RESULT"
    correct: bool
    team_id: str
    team_name: str
    score_delta: int
    new_score: int


class ScoreUpdate(BaseModel):
    type: Literal["SCORE_UPDATE"] = "SCORE_UPDATE"
    scores: dict[str, int]
    team_names: dict[str, str]


class GameStatusChange(BaseModel):
    type: Literal["GAME_STATUS"] = "GAME_STATUS"
    status: GameStatus


class FinalJeopardyClue(BaseModel):
    type: Literal["FINAL_JEOPARDY_CLUE"] = "FINAL_JEOPARDY_CLUE"
    category: str
    clue_text: str


class FinalJeopardyReveal(BaseModel):
    type: Literal["FINAL_REVEAL"] = "FINAL_REVEAL"
    results: list[dict]


class AnswerReveal(BaseModel):
    type: Literal["ANSWER_REVEAL"] = "ANSWER_REVEAL"
    answer: str


class DailyDouble(BaseModel):
    type: Literal["DAILY_DOUBLE"] = "DAILY_DOUBLE"
    team_id: str
    team_name: str
    category: str
    dollar_value: int


class TeamJoined(BaseModel):
    type: Literal["TEAM_JOINED"] = "TEAM_JOINED"
    team_id: str
    team_name: str


class ClueComplete(BaseModel):
    type: Literal["CLUE_COMPLETE"] = "CLUE_COMPLETE"


# --- Client -> Server Events ---


class BuzzIn(BaseModel):
    type: Literal["BUZZ"] = "BUZZ"
