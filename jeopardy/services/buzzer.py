from typing import Optional

from jeopardy.models.game import GameState


class BuzzerService:
    def open_buzz_window(self, game: GameState) -> None:
        game.buzz_window_open = True
        game.buzz_order = []
        game.current_answering_team = None

    def reopen_buzz_window(self, game: GameState) -> None:
        """Reopen buzz window after incorrect answer, keeping exclusion list."""
        game.buzz_window_open = True
        game.buzz_order = []
        game.current_answering_team = None

    def record_buzz(self, game: GameState, team_id: str) -> bool:
        """Record a buzz. Returns True if this team is the first (winner)."""
        if not game.buzz_window_open:
            return False
        if team_id in game.buzz_order:
            return False
        if team_id not in game.teams:
            return False
        if team_id in game.buzz_excluded_teams:
            return False

        game.buzz_order.append(team_id)

        if len(game.buzz_order) == 1:
            game.current_answering_team = team_id
            game.buzz_window_open = False
            return True
        return False

    def advance_to_next_buzzer(self, game: GameState) -> Optional[str]:
        """After incorrect answer, check if another team already buzzed in."""
        if not game.current_answering_team:
            return None
        try:
            current_idx = game.buzz_order.index(game.current_answering_team)
        except ValueError:
            return None
        next_idx = current_idx + 1
        if next_idx < len(game.buzz_order):
            next_team_id = game.buzz_order[next_idx]
            game.current_answering_team = next_team_id
            return next_team_id
        return None

    def close_buzz_window(self, game: GameState) -> None:
        game.buzz_window_open = False
