from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from jeopardy.dependencies import get_buzzer, get_game_manager, get_scoring
from jeopardy.models.events import (
    AnswerReveal,
    BoardUpdate,
    BuzzOpen,
    BuzzWinner,
    ClueComplete,
    ClueSelected,
    DailyDouble,
    FinalJeopardyClue,
    FinalJeopardyReveal,
    GameStatusChange,
    JudgeResult,
    ScoreUpdate,
    TeamJoined,
)
from jeopardy.models.game import GameStatus
from jeopardy.routes.websocket import ws_manager
from jeopardy.services.buzzer import BuzzerService
from jeopardy.services.game_manager import GameManager
from jeopardy.services.scoring import ScoringService

router = APIRouter(prefix="/api")


# --- Request schemas ---


class CreateTeamRequest(BaseModel):
    name: str


class SelectClueRequest(BaseModel):
    clue_id: str


class JudgeRequest(BaseModel):
    correct: bool


class FinalWagerRequest(BaseModel):
    team_token: str
    wager: int


class FinalAnswerRequest(BaseModel):
    team_token: str
    answer: str


class DailyDoubleWagerRequest(BaseModel):
    wager: int


class DailyDoubleJudgeRequest(BaseModel):
    correct: bool


# --- Endpoints ---


@router.post("/games")
async def create_game(gm: GameManager = Depends(get_game_manager)):
    try:
        game = await gm.create_game()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch clues from Notion: {e}")
    return {
        "game_id": game.game_id,
        "status": game.status,
        "categories": list(game.board.keys()),
    }


@router.get("/games/{game_id}")
async def get_game(game_id: str, gm: GameManager = Depends(get_game_manager)):
    game = gm.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return {
        "game_id": game.game_id,
        "status": game.status,
        "teams": [
            {"team_id": t.team_id, "name": t.name, "score": t.score}
            for t in game.teams.values()
        ],
        "board": gm.get_board_data(game, include_answers=False),
        "current_clue": {
            "clue_text": game.current_clue.clue_text,
            "category": game.current_clue.category,
            "dollar_value": game.current_clue.dollar_value,
        }
        if game.current_clue
        else None,
        "buzz_window_open": game.buzz_window_open,
    }


@router.post("/games/{game_id}/teams")
async def register_team(
    game_id: str,
    body: CreateTeamRequest,
    gm: GameManager = Depends(get_game_manager),
):
    game = gm.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    try:
        team = gm.add_team(game_id, body.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Broadcast team joined to host
    await ws_manager.broadcast_to_host(
        game_id,
        TeamJoined(team_id=team.team_id, team_name=team.name),
    )
    await ws_manager.broadcast_to_all(
        game_id,
        ScoreUpdate(scores=gm.get_scores(game), team_names=gm.get_team_names(game)),
    )

    return {
        "team_id": team.team_id,
        "team_token": team.team_token,
        "name": team.name,
    }


@router.get("/games/{game_id}/teams")
async def list_teams(game_id: str, gm: GameManager = Depends(get_game_manager)):
    game = gm.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return [
        {"team_id": t.team_id, "name": t.name, "score": t.score}
        for t in game.teams.values()
    ]


@router.post("/games/{game_id}/refetch")
async def refetch_clues(game_id: str, gm: GameManager = Depends(get_game_manager)):
    """Re-fetch clues from Notion and rebuild the board."""
    game = gm.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    try:
        await gm.refetch_clues(game_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch clues from Notion: {e}")

    await ws_manager.broadcast_to_host(
        game_id,
        BoardUpdate(
            board=gm.get_board_data(game, include_answers=True),
            scores=gm.get_scores(game),
            team_names=gm.get_team_names(game),
        ),
    )
    return {
        "categories": list(game.board.keys()),
        "total_clues": sum(len(c) for c in game.board.values()),
    }


@router.post("/games/{game_id}/start")
async def start_game(game_id: str, gm: GameManager = Depends(get_game_manager)):
    try:
        game = gm.start_game(game_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await ws_manager.broadcast_to_all(
        game_id,
        GameStatusChange(status=game.status),
    )
    await ws_manager.broadcast_to_host(
        game_id,
        BoardUpdate(
            board=gm.get_board_data(game, include_answers=True),
            scores=gm.get_scores(game),
            team_names=gm.get_team_names(game),
        ),
    )
    return {"status": game.status}


@router.post("/games/{game_id}/select")
async def select_clue(
    game_id: str,
    body: SelectClueRequest,
    gm: GameManager = Depends(get_game_manager),
    buzzer: BuzzerService = Depends(get_buzzer),
):
    try:
        clue = gm.select_clue(game_id, body.clue_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    game = gm.get_game(game_id)

    # Broadcast clue to all
    await ws_manager.broadcast_to_all(
        game_id,
        ClueSelected(
            clue_text=clue.clue_text,
            clue_image_url=clue.clue_image_url,
            category=clue.category,
            dollar_value=clue.dollar_value,
            is_daily_double=clue.is_daily_double,
        ),
    )

    # Send answer to host only
    await ws_manager.broadcast_to_host(
        game_id,
        AnswerReveal(answer=clue.answer),
    )

    if clue.is_daily_double:
        # Daily double: don't open buzz window
        game.daily_double_clue_id = clue.id
        await ws_manager.broadcast_to_all(
            game_id,
            DailyDouble(
                team_id="",
                team_name="",
                category=clue.category,
                dollar_value=clue.dollar_value,
            ),
        )
    else:
        # Regular clue: open buzz window
        buzzer.open_buzz_window(game)
        await ws_manager.broadcast_to_teams(game_id, BuzzOpen())

    return {
        "clue_text": clue.clue_text,
        "clue_image_url": clue.clue_image_url,
        "category": clue.category,
        "dollar_value": clue.dollar_value,
        "is_daily_double": clue.is_daily_double,
    }


@router.post("/games/{game_id}/judge")
async def judge_answer(
    game_id: str,
    body: JudgeRequest,
    gm: GameManager = Depends(get_game_manager),
    buzzer: BuzzerService = Depends(get_buzzer),
    scoring: ScoringService = Depends(get_scoring),
):
    game = gm.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if not game.current_clue:
        raise HTTPException(status_code=400, detail="No active clue")
    if not game.current_answering_team:
        raise HTTPException(status_code=400, detail="No team is answering")

    team_id = game.current_answering_team
    team = game.teams[team_id]

    if body.correct:
        new_score = scoring.apply_correct(game, team_id)
        delta = game.current_clue.dollar_value

        await ws_manager.broadcast_to_all(
            game_id,
            JudgeResult(
                correct=True,
                team_id=team_id,
                team_name=team.name,
                score_delta=delta,
                new_score=new_score,
            ),
        )
        await ws_manager.broadcast_to_all(
            game_id,
            ScoreUpdate(scores=gm.get_scores(game), team_names=gm.get_team_names(game)),
        )

        gm.mark_clue_answered(game_id)

        await ws_manager.broadcast_to_host(
            game_id,
            BoardUpdate(
                board=gm.get_board_data(game, include_answers=True),
                scores=gm.get_scores(game),
                team_names=gm.get_team_names(game),
            ),
        )
        await ws_manager.broadcast_to_all(game_id, ClueComplete())
    else:
        new_score = scoring.apply_incorrect(game, team_id)
        delta = -game.current_clue.dollar_value

        await ws_manager.broadcast_to_all(
            game_id,
            JudgeResult(
                correct=False,
                team_id=team_id,
                team_name=team.name,
                score_delta=delta,
                new_score=new_score,
            ),
        )
        await ws_manager.broadcast_to_all(
            game_id,
            ScoreUpdate(scores=gm.get_scores(game), team_names=gm.get_team_names(game)),
        )

        # Add to excluded teams
        game.buzz_excluded_teams.append(team_id)

        # Try next buzzer in queue
        next_team_id = buzzer.advance_to_next_buzzer(game)
        if next_team_id:
            next_team = game.teams[next_team_id]
            await ws_manager.broadcast_to_host(
                game_id,
                BuzzWinner(team_id=next_team_id, team_name=next_team.name),
            )
        else:
            # Reopen buzz window for remaining teams
            buzzer.reopen_buzz_window(game)
            await ws_manager.broadcast_to_teams(game_id, BuzzOpen())

    return {"correct": body.correct, "team_id": team_id, "new_score": new_score}


@router.post("/games/{game_id}/skip")
async def skip_clue(
    game_id: str,
    gm: GameManager = Depends(get_game_manager),
    buzzer: BuzzerService = Depends(get_buzzer),
):
    game = gm.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    buzzer.close_buzz_window(game)
    gm.skip_clue(game_id)

    await ws_manager.broadcast_to_host(
        game_id,
        BoardUpdate(
            board=gm.get_board_data(game, include_answers=True),
            scores=gm.get_scores(game),
            team_names=gm.get_team_names(game),
        ),
    )
    await ws_manager.broadcast_to_all(game_id, ClueComplete())
    return {"status": "skipped"}


@router.post("/games/{game_id}/final-jeopardy/start")
async def start_final_jeopardy(
    game_id: str,
    gm: GameManager = Depends(get_game_manager),
):
    try:
        game = gm.start_final_jeopardy(game_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await ws_manager.broadcast_to_all(
        game_id,
        GameStatusChange(status=GameStatus.FINAL_JEOPARDY),
    )

    # Find and broadcast the Final Jeopardy clue
    fj_clue = gm.get_final_jeopardy_clue(game_id)
    if fj_clue:
        game.current_clue = fj_clue
        await ws_manager.broadcast_to_all(
            game_id,
            FinalJeopardyClue(category=fj_clue.category, clue_text=fj_clue.clue_text),
        )
        # Send answer to host only
        await ws_manager.broadcast_to_host(
            game_id,
            AnswerReveal(answer=fj_clue.answer),
        )

    return {"status": game.status}


@router.post("/games/{game_id}/final-jeopardy/wager")
async def submit_final_wager(
    game_id: str,
    body: FinalWagerRequest,
    gm: GameManager = Depends(get_game_manager),
):
    game = gm.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.status != GameStatus.FINAL_JEOPARDY:
        raise HTTPException(status_code=400, detail="Not in Final Jeopardy")

    team = gm.get_team_by_token(game_id, body.team_token)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    if body.wager < 0 or body.wager > max(team.score, 0):
        raise HTTPException(
            status_code=400,
            detail=f"Wager must be between 0 and {max(team.score, 0)}",
        )

    team.final_wager = body.wager

    # Notify host that a wager has been submitted
    await ws_manager.broadcast_to_host(
        game_id,
        ScoreUpdate(scores=gm.get_scores(game), team_names=gm.get_team_names(game)),
    )

    return {"team_id": team.team_id, "wager": body.wager}


@router.post("/games/{game_id}/final-jeopardy/answer")
async def submit_final_answer(
    game_id: str,
    body: FinalAnswerRequest,
    gm: GameManager = Depends(get_game_manager),
):
    game = gm.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.status != GameStatus.FINAL_JEOPARDY:
        raise HTTPException(status_code=400, detail="Not in Final Jeopardy")

    team = gm.get_team_by_token(game_id, body.team_token)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    team.final_answer = body.answer

    # Notify host
    await ws_manager.broadcast_to_host(
        game_id,
        ScoreUpdate(scores=gm.get_scores(game), team_names=gm.get_team_names(game)),
    )

    return {"team_id": team.team_id, "answer_submitted": True}


@router.post("/games/{game_id}/final-jeopardy/reveal")
async def reveal_final_jeopardy(
    game_id: str,
    gm: GameManager = Depends(get_game_manager),
    scoring: ScoringService = Depends(get_scoring),
):
    """Host triggers reveal of all Final Jeopardy answers and scoring."""
    game = gm.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    results = []
    for team in game.teams.values():
        # Host will judge each answer; for now just reveal
        results.append(
            {
                "team_id": team.team_id,
                "team_name": team.name,
                "wager": team.final_wager,
                "answer": team.final_answer,
                "score": team.score,
            }
        )

    await ws_manager.broadcast_to_all(
        game_id,
        FinalJeopardyReveal(results=results),
    )

    return {"results": results}


@router.post("/games/{game_id}/final-jeopardy/judge/{team_id}")
async def judge_final_answer(
    game_id: str,
    team_id: str,
    body: JudgeRequest,
    gm: GameManager = Depends(get_game_manager),
    scoring: ScoringService = Depends(get_scoring),
):
    """Host judges a specific team's Final Jeopardy answer."""
    game = gm.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if team_id not in game.teams:
        raise HTTPException(status_code=404, detail="Team not found")

    new_score = scoring.apply_final_wager(game, team_id, body.correct)

    await ws_manager.broadcast_to_all(
        game_id,
        ScoreUpdate(scores=gm.get_scores(game), team_names=gm.get_team_names(game)),
    )

    # Check if all teams have been judged, then finish
    return {"team_id": team_id, "correct": body.correct, "new_score": new_score}


@router.get("/games/{game_id}/team-state/{team_token}")
async def get_team_state(
    game_id: str,
    team_token: str,
    gm: GameManager = Depends(get_game_manager),
):
    """Get a team's current state for reconnection (FJ submission status)."""
    game = gm.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    team = gm.get_team_by_token(game_id, team_token)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return {
        "final_wager": team.final_wager,
        "has_final_answer": team.final_answer is not None,
    }


@router.post("/games/{game_id}/finish")
async def finish_game(game_id: str, gm: GameManager = Depends(get_game_manager)):
    try:
        game = gm.finish_game(game_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await ws_manager.broadcast_to_all(
        game_id,
        GameStatusChange(status=GameStatus.FINISHED),
    )
    await ws_manager.broadcast_to_all(
        game_id,
        ScoreUpdate(scores=gm.get_scores(game), team_names=gm.get_team_names(game)),
    )
    return {"status": game.status}
