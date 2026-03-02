import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from jeopardy.models.events import (
    BuzzLocked,
    BuzzTimeout,
    BuzzWinner,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.host_connections: dict[str, list[WebSocket]] = {}
        self.team_connections: dict[str, dict[str, WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect_host(self, game_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self.host_connections.setdefault(game_id, []).append(ws)

    async def connect_team(self, game_id: str, team_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            game_teams = self.team_connections.setdefault(game_id, {})
            # Replace existing connection (reconnection)
            game_teams[team_id] = ws

    async def disconnect_host(self, game_id: str, ws: WebSocket) -> None:
        async with self._lock:
            conns = self.host_connections.get(game_id, [])
            if ws in conns:
                conns.remove(ws)

    async def disconnect_team(self, game_id: str, team_id: str, ws: WebSocket | None = None) -> None:
        async with self._lock:
            teams = self.team_connections.get(game_id, {})
            # Only remove if the WebSocket matches (prevents stale handlers
            # from removing a newer reconnected WebSocket)
            if ws is None or teams.get(team_id) is ws:
                teams.pop(team_id, None)

    async def broadcast_to_host(self, game_id: str, event: BaseModel) -> None:
        msg = event.model_dump_json()
        dead: list[WebSocket] = []
        for ws in self.host_connections.get(game_id, []):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect_host(game_id, ws)

    async def broadcast_to_teams(self, game_id: str, event: BaseModel) -> None:
        msg = event.model_dump_json()
        dead: list[tuple[str, WebSocket]] = []
        for team_id, ws in self.team_connections.get(game_id, {}).items():
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append((team_id, ws))
        for team_id, ws in dead:
            await self.disconnect_team(game_id, team_id, ws)

    async def send_to_team(self, game_id: str, team_id: str, event: BaseModel) -> None:
        ws = self.team_connections.get(game_id, {}).get(team_id)
        if ws:
            try:
                await ws.send_text(event.model_dump_json())
            except Exception:
                await self.disconnect_team(game_id, team_id, ws)

    async def broadcast_to_all(self, game_id: str, event: BaseModel) -> None:
        await asyncio.gather(
            self.broadcast_to_host(game_id, event),
            self.broadcast_to_teams(game_id, event),
        )


ws_manager = ConnectionManager()


@router.websocket("/ws/host/{game_id}")
async def host_websocket(websocket: WebSocket, game_id: str) -> None:
    from jeopardy.services.game_manager import GameManager

    gm: GameManager = websocket.app.state.game_manager
    game = gm.get_game(game_id)
    if not game:
        await websocket.close(code=4004, reason="Game not found")
        return

    await ws_manager.connect_host(game_id, websocket)

    # Send full state sync on connect/reconnect
    for event in gm.get_host_sync_events(game):
        try:
            await websocket.send_text(event.model_dump_json())
        except Exception:
            await ws_manager.disconnect_host(game_id, websocket)
            return

    try:
        while True:
            # Host WS is primarily server -> client
            # Keep alive by receiving messages
            data = await websocket.receive_text()
            # Could handle host control messages if needed
            logger.debug("Host message for game %s: %s", game_id, data)
    except WebSocketDisconnect:
        await ws_manager.disconnect_host(game_id, websocket)


@router.websocket("/ws/team/{game_id}/{team_token}")
async def team_websocket(websocket: WebSocket, game_id: str, team_token: str) -> None:
    from jeopardy.services.game_manager import GameManager
    from jeopardy.services.buzzer import BuzzerService

    gm: GameManager = websocket.app.state.game_manager
    buzzer: BuzzerService = websocket.app.state.buzzer

    team = gm.get_team_by_token(game_id, team_token)
    if not team:
        await websocket.close(code=4001, reason="Invalid team token")
        return

    game = gm.get_game(game_id)
    if not game:
        await websocket.close(code=4004, reason="Game not found")
        return

    await ws_manager.connect_team(game_id, team.team_id, websocket)

    # Send full state sync on connect/reconnect
    for event in gm.get_team_sync_events(game, team.team_id):
        await ws_manager.send_to_team(game_id, team.team_id, event)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")

            if msg_type == "BUZZ":
                is_winner = buzzer.record_buzz(game, team.team_id)
                if is_winner:
                    team_name = game.teams[team.team_id].name
                    await ws_manager.broadcast_to_host(
                        game_id,
                        BuzzWinner(team_id=team.team_id, team_name=team_name),
                    )
                    await ws_manager.broadcast_to_teams(
                        game_id,
                        BuzzLocked(team_name=team_name),
                    )
    except WebSocketDisconnect:
        await ws_manager.disconnect_team(game_id, team.team_id, websocket)
