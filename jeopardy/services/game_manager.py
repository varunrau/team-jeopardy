from typing import Optional

from jeopardy.config import settings
from jeopardy.models.game import Clue, GameState, GameStatus, Team
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
        if game.status != GameStatus.LOBBY:
            raise ValueError("Cannot add teams after game has started")
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

    def mark_clue_answered(self, game_id: str) -> None:
        game = self._require_game(game_id)
        if game.current_clue:
            for clues in game.board.values():
                for c in clues:
                    if c.id == game.current_clue.id:
                        c.is_answered = True
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
                entry: dict = {
                    "id": clue.id,
                    "dollar_value": clue.dollar_value,
                    "is_answered": clue.is_answered,
                    "is_daily_double": clue.is_daily_double,
                    "category": clue.category,
                }
                if include_answers:
                    entry["answer"] = clue.answer
                    entry["clue_text"] = clue.clue_text
                board_data[category].append(entry)
        return board_data

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
