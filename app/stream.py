import asyncio

from aiortc import VideoStreamTrack
from aiortc.contrib.media import MediaRelay
from av import VideoFrame

fps = 30


class StreamManager:
    def __init__(self):
        self.capturers = {}
        self.relays = {}
        self.base_tracks = {}
        self.tracks = {}

    def setup(self, mode, capture_fn, num_track):
        self.capturers[mode] = FrameCapturer(capture_fn)
        self.relays[mode] = MediaRelay()

        # self.base_tracks[mode] = [ImageStreamTrack(self.capturers[mode], i) for i in range(num_track)]
        # self.tracks[mode] = [self.relays[mode].subscribe(track) for track in self.base_tracks[mode]]
        self.num_track = num_track

    def get_tracks(self, mode):
        # TODO
        # tracks = [self.relays[mode].subscribe(track) for track in self.base_tracks[mode]]
        # return tracks

        self.base_tracks[mode] = [ImageStreamTrack(self.capturers[mode], i) for i in range(self.num_track)]
        self.tracks[mode] = [self.relays[mode].subscribe(track) for track in self.base_tracks[mode]]
        return self.tracks[mode]

    async def cleanup(self, mode):
        if mode in self.tracks:
            del self.tracks[mode]
        if mode in self.base_tracks:
            for track in self.base_tracks[mode]:
                track.stop()
            del self.base_tracks[mode]
        if mode in self.relays:
            del self.relays[mode]
        if mode in self.capturers:
            await self.capturers[mode].stop()
            del self.capturers[mode]


class FrameCapturer:
    def __init__(self, capture_fn):
        self.frame = None
        self.callbacks = {}
        self.capture_fn = capture_fn
        self.task = asyncio.create_task(self.update_frame())

    async def update_frame(self):
        while True:
            self.frame = self.capture_fn()
            for callback in self.callbacks.values():
                callback(self.frame)
            await asyncio.sleep(1 / fps)  # TODO: consider processing time?

    async def stop(self):
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass
        print("Frame capturer stopped")

    def subscribe(self, key, callback):
        self.callbacks[key] = callback

    def unsubscribe(self, key):
        if key in self.callbacks:
            del self.callbacks[key]
            print(f"unsubscribed {key}")


class ImageStreamTrack(VideoStreamTrack):
    def __init__(self, capturer: FrameCapturer, camera_idx: int):
        super().__init__()
        self.key = f"rgb:franka{camera_idx}_front_cam:256x256:2d"
        self.frame = None
        self.capturer = capturer
        self.capturer.subscribe(self.id, self.on_frame)

    async def recv(self):
        pts, time_base = await self.next_timestamp()  # 30fps
        while self.frame is None:
            await asyncio.sleep(0.1)
        frame = VideoFrame.from_ndarray(self.frame, format="rgb24")
        frame.pts = pts
        frame.time_base = time_base
        return frame

    def on_frame(self, frame):
        # self.frame = frame[self.key]
        if frame is not None and self.key in frame:
            self.frame = frame[self.key]

    def stop(self):
        self.capturer.unsubscribe(self.id)
        super().stop()
