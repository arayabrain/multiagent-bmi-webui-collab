import asyncio

import numpy as np
import reactivex as rx
import socketio
from reactivex import operators as ops
from typing import Union, Tuple

from app.devices.utils.networking import extract_buffer
from app.devices.utils.utils import array2str


class Decoder:
    """Decode the EEG signal using a model."""

    def __init__(
        self,
        input_observable: rx.Observable,
        model,
        window_size: int,
        window_step: Union[int, None] = None,
    ) -> None:
        self.input_observable = input_observable
        self.subscription = None
        self.is_running = False

        self.model = model
        self.window_size = window_size
        self.window_step = window_step
        self.loop = asyncio.get_event_loop()
        self.sio: socketio.AsyncServer | None = None

    def set_socket(self, sio: socketio.AsyncServer) -> None:
        self.sio = sio

    def start(self) -> None:
        if self.is_running:
            print("Decoder is already running.")
            return

        self.subscription = self.input_observable.pipe(  # type: ignore
            ops.buffer_with_count(self.window_size, self.window_step),  # list of (time, channels)
            ops.map(lambda buf: extract_buffer(buf)[0]),  # type: ignore  # (time, channels)
            ops.map(self._decode),
        ).subscribe(
            on_next=self._publish,
            on_completed=self.stop,
        )
        self.is_running = True

    def _decode(self, data: np.ndarray) -> Tuple[Union[int, None], np.ndarray]:
        return self.model(data)

    def _publish(self, data: Tuple[Union[int, None], np.ndarray]) -> None:
        if self.loop.is_closed():
            return

        class_id, likelihoods = data
        self.loop.create_task(self._emit(class_id, likelihoods))

        class_str = f"{class_id:>4}" if class_id is not None else "None"
        likelihoods_str = array2str(likelihoods)
        print(f"EEG class: {class_str}, likelihoods: {likelihoods_str} ")  # trailing space in case of no line break

    async def _emit(self, class_id: Union[int, None], likelihoods: np.ndarray) -> None:
            assert isinstance(self.sio, socketio.AsyncServer), "Socket is not set."
            await self.sio.emit("eeg", {"classId": class_id, "likelihoods": likelihoods.tolist()})

    def stop(self) -> None:
        if self.subscription is not None:
            self.subscription.dispose()
        self.is_running = False
        print("Decoder stopped.")
