from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.app_state import AppState
from app.routes import browser

host = "0.0.0.0"
# host = "127.0.0.1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(lifespan=lifespan)
app.state = AppState()  # global state for the app
app.include_router(browser.router)
app_dir = Path(__file__).parent
app.mount("/static", StaticFiles(directory=app_dir / "static"), name="static")
templates = Jinja2Templates(directory=app_dir / "templates")


@app.get("/")
async def get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "num_agents": app.state.num_agents})


if __name__ == "__main__":
    import uvicorn

    # for HTTPS
    # key_dir = app_dir / "../.keys"

    uvicorn.run(
        "main:app",
        host=host,
        port=8000,
        # ssl_keyfile=key_dir / "server.key",
        # ssl_certfile=key_dir / "server.crt",
    )
