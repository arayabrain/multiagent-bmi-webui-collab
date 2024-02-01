import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import zmq.asyncio
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from mabui.app.app_state import AppState
from mabui.routes import browser
from mabui.routes.eeg_command_sub import eeg_command_sub


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    A context manager that manages the lifespan of the application.
    It performs startup and shutdown actions when entering and exiting the context.
    """

    zmq_context = zmq.asyncio.Context()
    socket = zmq_context.socket(zmq.SUB)
    socket.bind("tcp://127.0.0.1:5555")
    socket.setsockopt(zmq.SUBSCRIBE, b"")

    eeg_task = asyncio.create_task(eeg_command_sub(socket, app.state.update_command))
    print("eeg_listener started")

    yield

    eeg_task.cancel()
    await eeg_task
    socket.close()
    zmq_context.term()


app = FastAPI(lifespan=lifespan)
app.state = AppState()  # global state for the app
app.include_router(browser.router)
root = Path(__file__).parent.parent
app.mount("/static", StaticFiles(directory=root / "static"), name="static")
templates = Jinja2Templates(directory=root / "templates")


@app.get("/")
async def get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "num_agents": app.state.num_agents})


if __name__ == "__main__":
    import sys

    if sys.platform == "win32":
        # deal with a zmq warning on Windows
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    import uvicorn

    uvicorn.run("main:app", host="localhost", port=8000)
