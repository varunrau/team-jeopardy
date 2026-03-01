import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from jeopardy.routes import api, views, websocket
from jeopardy.services.buzzer import BuzzerService
from jeopardy.services.game_manager import GameManager
from jeopardy.services.scoring import ScoringService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.game_manager = GameManager()
    app.state.buzzer = BuzzerService()
    app.state.scoring = ScoringService()
    app.state.templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    logger.info("Jeopardy server started")
    yield
    # Shutdown
    logger.info("Jeopardy server shutting down")


app = FastAPI(title="Team Jeopardy", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(api.router)
app.include_router(websocket.router)
app.include_router(views.router)


if __name__ == "__main__":
    import uvicorn
    from jeopardy.config import settings

    uvicorn.run(
        "jeopardy.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
