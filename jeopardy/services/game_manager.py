from typing import Optional

from pydantic import BaseModel

from jeopardy.config import settings
from jeopardy.models.game import Clue, GameState, GameStatus, Team
from jeopardy.models.events import (
    AnswerReveal,
    BoardUpdate,
    BuzzLocked,
    BuzzOpen,
    BuzzWinner,
    ClueSelected,
    DailyDouble,
    FinalJeopardyClue,
    GameStatusChange,
    ScoreUpdate,
)
from jeopardy.services.notion import NotionService


class GameManager:
    def __init__(self) -> None:
        self.games: dict[str, GameState] = {}
        self.notion = NotionService()

    async def create_game(self) -> GameState:
        clues = await self.notion.fetch_clues()
        board = self._build_board(clues)
        game = GameState(board=board)
        self.games[game.game_id] = game
        return game

    async def refetch_clues(self, game_id: str) -> GameState:
        game = self._require_game(game_id)
        clues = await self.notion.fetch_clues()
        game.board = self._build_board(clues)
        game.current_clue = None
        game.buzz_window_open = False
        game.buzz_order = []
        game.buzz_excluded_teams = []
        game.current_answering_team = None
        return game

    def get_game(self, game_id: str) -> Optional[GameState]:
        return self.games.get(game_id)

    def add_team(self, game_id: str, name: str) -> Team:
        game = self._require_game(game_id)
        if len(game.teams) >= settings.max_teams:
            raise ValueError("Maximum number of teams reached")
        team = Team(name=name)
        game.teams[team.team_id] = team
        return team

    def start_game(self, game_id: str) -> GameState:
        game = self._require_game(game_id)
        if game.status != GameStatus.LOBBY:
            raise ValueError("Game is not in lobby")
        if len(game.teams) < 1:
            raise ValueError("Need at least one team to start")
        game.status = GameStatus.IN_PROGRESS
        return game

    def select_clue(self, game_id: str, clue_id: str) -> Clue:
        game = self._require_game(game_id)
        if game.status != GameStatus.IN_PROGRESS:
            raise ValueError("Game is not in progress")
        for category_clues in game.board.values():
            for clue in category_clues:
                if clue.id == clue_id and not clue.is_answered:
                    game.current_clue = clue
                    game.buzz_order = []
                    game.buzz_excluded_teams = []
                    game.current_answering_team = None
                    game.buzz_window_open = False
                    return clue
        raise ValueError("Clue not found or already answered")

    def mark_clue_answered(self, game_id: str, team_id: str | None = None) -> None:
        game = self._require_game(game_id)
        if game.current_clue:
            for clues in game.board.values():
                for c in clues:
                    if c.id == game.current_clue.id:
                        c.is_answered = True
                        c.answered_by_team_id = team_id
            game.current_clue = None
            game.buzz_window_open = False
            game.buzz_order = []
            game.buzz_excluded_teams = []
            game.current_answering_team = None

    def skip_clue(self, game_id: str) -> None:
        """Skip the current clue without marking it answered (no one buzzed)."""
        game = self._require_game(game_id)
        if game.current_clue:
            # Mark as answered so it's removed from the board
            for clues in game.board.values():
                for c in clues:
                    if c.id == game.current_clue.id:
                        c.is_answered = True
            game.current_clue = None
            game.buzz_window_open = False
            game.buzz_order = []
            game.buzz_excluded_teams = []
            game.current_answering_team = None

    def start_final_jeopardy(self, game_id: str) -> GameState:
        game = self._require_game(game_id)
        game.status = GameStatus.FINAL_JEOPARDY
        game.current_clue = None
        game.buzz_window_open = False
        return game

    def finish_game(self, game_id: str) -> GameState:
        game = self._require_game(game_id)
        game.status = GameStatus.FINISHED
        return game

    def get_team_by_token(self, game_id: str, team_token: str) -> Optional[Team]:
        game = self.games.get(game_id)
        if not game:
            return None
        for team in game.teams.values():
            if team.team_token == team_token:
                return team
        return None

    def get_final_jeopardy_clue(self, game_id: str) -> Optional[Clue]:
        """Find the Final Jeopardy clue from the board."""
        game = self._require_game(game_id)
        for category, clues in game.board.items():
            for clue in clues:
                if category.lower().startswith("final"):
                    return clue
        return None

    def all_clues_answered(self, game_id: str) -> bool:
        game = self._require_game(game_id)
        for clues in game.board.values():
            for clue in clues:
                # Skip Final Jeopardy clues in this check
                if clue.category.lower().startswith("final"):
                    continue
                if not clue.is_answered:
                    return False
        return True

    def all_final_answers_in(self, game_id: str) -> bool:
        game = self._require_game(game_id)
        for team in game.teams.values():
            if team.score > 0 and team.final_answer is None:
                return False
        return True

    def get_scores(self, game: GameState) -> dict[str, int]:
        return {tid: t.score for tid, t in game.teams.items()}

    def get_team_names(self, game: GameState) -> dict[str, str]:
        return {tid: t.name for tid, t in game.teams.items()}

    def get_board_data(self, game: GameState, include_answers: bool = False) -> dict[str, list[dict]]:
        """Serialize board for WebSocket broadcast."""
        board_data: dict[str, list[dict]] = {}
        for category, clues in game.board.items():
            board_data[category] = []
            for clue in clues:
                answered_by_name = None
                if clue.answered_by_team_id and clue.answered_by_team_id in game.teams:
                    answered_by_name = game.teams[clue.answered_by_team_id].name
                entry: dict = {
                    "id": clue.id,
                    "dollar_value": clue.dollar_value,
                    "is_answered": clue.is_answered,
                    "is_daily_double": clue.is_daily_double,
                    "category": clue.category,
                    "answered_by": answered_by_name,
                }
                if include_answers:
                    entry["answer"] = clue.answer
                    entry["clue_text"] = clue.clue_text
                board_data[category].append(entry)
        return board_data

    def get_team_sync_events(self, game: GameState, team_id: str) -> list[BaseModel]:
        """Build events to sync a reconnecting team client."""
        events: list[BaseModel] = []

        events.append(ScoreUpdate(
            scores=self.get_scores(game),
            team_names=self.get_team_names(game),
        ))
        events.append(GameStatusChange(status=game.status))

        if game.status == GameStatus.IN_PROGRESS and game.current_clue:
            clue = game.current_clue
            events.append(ClueSelected(
                clue_text=clue.clue_text,
                clue_image_url=clue.clue_image_url,
                category=clue.category,
                dollar_value=clue.dollar_value,
                is_daily_double=clue.is_daily_double,
            ))
            if clue.is_daily_double:
                events.append(DailyDouble(
                    team_id="",
                    team_name="",
                    category=clue.category,
                    dollar_value=clue.dollar_value,
                ))
            elif game.buzz_window_open:
                if team_id not in game.buzz_excluded_teams:
                    events.append(BuzzOpen())
            elif game.current_answering_team:
                answering_team = game.teams.get(game.current_answering_team)
                if answering_team:
                    events.append(BuzzLocked(team_name=answering_team.name))

        if game.status == GameStatus.FINAL_JEOPARDY:
            fj_clue = self.get_final_jeopardy_clue(game.game_id)
            if fj_clue:
                events.append(FinalJeopardyClue(
                    category=fj_clue.category,
                    clue_text=fj_clue.clue_text,
                ))

        return events

    def get_host_sync_events(self, game: GameState) -> list[BaseModel]:
        """Build events to sync a reconnecting host client."""
        events: list[BaseModel] = []

        events.append(BoardUpdate(
            board=self.get_board_data(game, include_answers=True),
            scores=self.get_scores(game),
            team_names=self.get_team_names(game),
        ))

        if game.status == GameStatus.FINISHED:
            events.append(GameStatusChange(status=game.status))
            return events

        if game.status == GameStatus.IN_PROGRESS and game.current_clue:
            clue = game.current_clue
            events.append(ClueSelected(
                clue_text=clue.clue_text,
                clue_image_url=clue.clue_image_url,
                category=clue.category,
                dollar_value=clue.dollar_value,
                is_daily_double=clue.is_daily_double,
            ))
            events.append(AnswerReveal(answer=clue.answer))
            if clue.is_daily_double:
                events.append(DailyDouble(
                    team_id="",
                    team_name="",
                    category=clue.category,
                    dollar_value=clue.dollar_value,
                ))
            if game.current_answering_team:
                answering_team = game.teams.get(game.current_answering_team)
                if answering_team:
                    events.append(BuzzWinner(
                        team_id=game.current_answering_team,
                        team_name=answering_team.name,
                    ))

        if game.status == GameStatus.FINAL_JEOPARDY:
            events.append(GameStatusChange(status=game.status))
            fj_clue = self.get_final_jeopardy_clue(game.game_id)
            if fj_clue:
                events.append(FinalJeopardyClue(
                    category=fj_clue.category,
                    clue_text=fj_clue.clue_text,
                ))
                events.append(AnswerReveal(answer=fj_clue.answer))

        return events

    def _build_board(self, clues: list[Clue]) -> dict[str, list[Clue]]:
        board: dict[str, list[Clue]] = {}
        for clue in clues:
            board.setdefault(clue.category, []).append(clue)
        for cat in board:
            board[cat].sort(key=lambda c: c.dollar_value)
        return board

    def _require_game(self, game_id: str) -> GameState:
        game = self.games.get(game_id)
        if not game:
            raise ValueError(f"Game {game_id} not found")
        return game
