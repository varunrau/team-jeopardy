from jeopardy.models.game import GameState


class ScoringService:
    def apply_correct(self, game: GameState, team_id: str) -> int:
        team = game.teams[team_id]
        value = game.current_clue.dollar_value
        team.score += value
        return team.score

    def apply_incorrect(self, game: GameState, team_id: str) -> int:
        team = game.teams[team_id]
        value = game.current_clue.dollar_value
        team.score -= value
        return team.score

    def apply_daily_double(self, game: GameState, team_id: str, wager: int, correct: bool) -> int:
        team = game.teams[team_id]
        if correct:
            team.score += wager
        else:
            team.score -= wager
        return team.score

    def apply_final_wager(self, game: GameState, team_id: str, correct: bool) -> int:
        team = game.teams[team_id]
        wager = team.final_wager or 0
        if correct:
            team.score += wager
        else:
            team.score -= wager
        return team.score
