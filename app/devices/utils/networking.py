"""Networking utils
from https://github.com/arayabrain/human-robot-interface/blob/main/src/networking.py
"""

import threading
import time
from typing import Callable

import numpy as np
import pylsl
import reactivex as rx
import socketio
from pylsl import LostError, StreamInfo, StreamInlet, StreamOutlet, local_clock
from reactivex import operators as ops
from typing import List, Tuple


# Gets a specified stream from stream information and creates a stream inlet
def get_stream_inlet(stream_infos: List[StreamInfo], **kwargs) -> StreamInlet:
    assert len(kwargs) >= 1, "No stream filter provided"

    for stream_info in stream_infos:
        # Find a stream that matches all attributes provided for filtering
        if all(getattr(stream_info, key)() == value for key, value in kwargs.items()):
            # Create inlet with preprocessing
            # (https://labstreaminglayer.readthedocs.io/projects/liblsl/ref/enums.html#_CPPv424lsl_processing_options_t)
            inlet = StreamInlet(stream_info, processing_flags=pylsl.proc_clocksync | pylsl.proc_dejitter)
            # TODO: Set max_buflen based on seconds needed?
            return inlet

    raise LookupError(f"Stream with filter {kwargs} not found")


# Creates a stream outlet; if sampling rate is 0 then it is irregular; a unique name enables stream resumption
def create_stream_outlet(
    name: str, type: str, channel_count: int, nominal_srate: int, channel_format: str
) -> StreamOutlet:
    assert channel_count >= 1, "Channel count must be >= 1"
    assert nominal_srate >= 0, "Sampling rate must be 0 or >= 1"

    info = StreamInfo(
        name=name,
        type=type,
        channel_count=channel_count,
        nominal_srate=nominal_srate,
        channel_format=channel_format,
        source_id=name,
    )
    return StreamOutlet(info)


# Creates a hot observable that forwards data from an LSL stream, using threading to run asynchronously
def create_observable_from_stream_inlet(stream: StreamInlet) -> rx.Observable:

    def push_chunks(
        observer: rx.Observer,
        scheduler: rx.scheduler.scheduler.Scheduler,
    ) -> Callable[[], None]:
        stop_event = threading.Event()  # Create signal that can be used to stop thread when done

        # Function to forward data chunks that can be run in a thread
        def push_chunks_thread():
            while not stop_event.is_set():
                try:
                    chunk, timestamps = stream.pull_chunk()  # Pulls a chunk of data (as long as stream is available)
                    if timestamps:
                        for value, timestamp in zip(chunk, timestamps):
                            observer.on_next((value, timestamp))
                except LostError:
                    # If the LSL stream is lost then catch the error and raise it in the observer
                    observer.on_error("Stream lost")
                    break

        # Disposal function for subscription cleanup (called automatically once subscription is over)
        def dispose():
            stop_event.set()  # Signal to stop loop in thread

        thread = threading.Thread(target=push_chunks_thread)
        thread.start()  # Start thread that forwards LSL stream data to the subscribed observer

        return dispose

    return rx.create(push_chunks).pipe(ops.share())


def extract_buffer(buf: list) -> Tuple:
    """Extract data and timestamps from the buffer.
    Args:
        buf: list of Tuple (data, timestamp)
            data: list of float, shape (channels,)
            timestamp: float
    Returns:
        data: np.ndarray, shape (time, channels)  # time = len(buf)
        timestamps: np.ndarray, shape (time,)
    """
    data, timestamps = zip(*buf)
    data = np.array(data, dtype=float)  # TODO: float32 or 64?
    timestamps = np.array(timestamps, dtype=float)
    return data, timestamps


async def get_ref_time(sio: socketio.AsyncServer, sid: str, num_rtt_measurements: int = 10):
    # measure round-trip time for data collection
    async def measure_rtt():
        start_time = time.time()
        await sio.call("ping", to=sid)
        rtt = (time.time() - start_time) * 1000  # msec
        return rtt

    rtts = np.array([await measure_rtt() for _ in range(num_rtt_measurements)])
    rtt_avg = np.mean(rtts)
    print(f"RTT: {rtt_avg:.1f} +/- {np.std(rtts):.1f} ms")

    # get the reference times from the browser and LSL
    # should be the same timing as much as possible
    ref_time_lsl = local_clock()  # first get LSL time
    ref_time_browser = await sio.call("getTime", to=sid) - rtt_avg / 2  # then get RTT-corrected browser time

    return ref_time_lsl, ref_time_browser
