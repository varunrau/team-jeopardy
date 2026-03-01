import base64
import io

import qrcode
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()


def _generate_qr_data_uri(url: str) -> str:
    qr = qrcode.make(url)
    buffer = io.BytesIO()
    qr.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse("home.html", {"request": request})


@router.get("/host/{game_id}", response_class=HTMLResponse)
async def host_view(request: Request, game_id: str):
    templates = request.app.state.templates
    gm = request.app.state.game_manager
    game = gm.get_game(game_id)
    if not game:
        return HTMLResponse("Game not found", status_code=404)

    return templates.TemplateResponse(
        "host.html",
        {
            "request": request,
            "game_id": game_id,
            "game": game,
        },
    )


@router.get("/play/{game_id}/{team_token}", response_class=HTMLResponse)
async def team_view(request: Request, game_id: str, team_token: str):
    templates = request.app.state.templates
    gm = request.app.state.game_manager
    team = gm.get_team_by_token(game_id, team_token)
    if not team:
        return HTMLResponse("Invalid team link", status_code=404)

    game = gm.get_game(game_id)
    return templates.TemplateResponse(
        "team.html",
        {
            "request": request,
            "game_id": game_id,
            "team_token": team_token,
            "team": team,
            "game": game,
        },
    )


@router.get("/lobby/{game_id}", response_class=HTMLResponse)
async def lobby_view(request: Request, game_id: str):
    templates = request.app.state.templates
    gm = request.app.state.game_manager
    game = gm.get_game(game_id)
    if not game:
        return HTMLResponse("Game not found", status_code=404)

    # Generate QR codes for existing teams
    base_url = str(request.base_url).rstrip("/")
    team_qr_codes = {}
    for team in game.teams.values():
        url = f"{base_url}/play/{game_id}/{team.team_token}"
        team_qr_codes[team.team_id] = {
            "name": team.name,
            "url": url,
            "qr": _generate_qr_data_uri(url),
        }

    return templates.TemplateResponse(
        "lobby.html",
        {
            "request": request,
            "game_id": game_id,
            "game": game,
            "team_qr_codes": team_qr_codes,
        },
    )
