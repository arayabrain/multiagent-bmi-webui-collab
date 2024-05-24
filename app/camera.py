import asyncio

from aiortc import VideoStreamTrack
from av import VideoFrame

fps = 30


class FrameCapturer:
    _instance: "FrameCapturer | None" = None

    def __new__(cls, capture_fn):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.frame = None
            cls._instance.callbacks = []
            cls._instance.capture_fn = capture_fn
            asyncio.create_task(cls._instance.update_frame())
        return cls._instance

    async def update_frame(self):
        while True:
            self.frame = self.capture_fn()
            for callback in self.callbacks:
                callback(self.frame)
            await asyncio.sleep(1 / fps)  # TODO: consider processing time?

    def subscribe(self, callback):
        self.callbacks.append(callback)


class ImageStreamTrack(VideoStreamTrack):
    def __init__(self, capture_fn, camera_idx: int):
        super().__init__()
        self.key = f"rgb:franka{camera_idx}_front_cam:256x256:2d"
        self.frame = None
        self.capturer = FrameCapturer(capture_fn)
        self.capturer.subscribe(self.on_frame)

    async def recv(self):
        pts, time_base = await self.next_timestamp()  # 30fps
        while self.frame is None:
            await asyncio.sleep(0.1)
        frame = VideoFrame.from_ndarray(self.frame, format="rgb24")
        frame.pts = pts
        frame.time_base = time_base
        return frame

    def on_frame(self, frame):
        self.frame = frame[self.key]

    # TODO: unsubscribe
