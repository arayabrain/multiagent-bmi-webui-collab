"""Networking utils
from https://github.com/arayabrain/human-robot-interface/blob/main/src/networking.py
"""

import threading
from typing import Callable

import pylsl
import reactivex
from pylsl import LostError, StreamInfo, StreamInlet, StreamOutlet


# Gets a specified stream from stream information and creates a stream inlet
def get_stream_inlet(stream_infos: list[StreamInfo], **kwargs) -> StreamInlet:
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
def create_observable_from_stream_inlet(stream: StreamInlet) -> reactivex.Observable:

    def push_chunks(
        observer: reactivex.Observer,
        scheduler: reactivex.scheduler.scheduler.Scheduler,
    ) -> Callable[[], None]:
        stop_event = threading.Event()  # Create signal that can be used to stop thread when done

        # Function to forward data chunks that can be run in a thread
        def push_chunks_thread():
            while True:
                try:
                    chunk, timestamps = stream.pull_chunk()  # Pulls a chunk of data (as long as stream is available)
                    if timestamps:
                        [observer.on_next(c) for c in chunk]
                        # Send one item at a time
                        # TODO: Do we need to account for latencies, delays, different OSs, etc.?
                        # Currently timestamps are ignored beyond this point
                except LostError:
                    observer.on_error("Stream lost")
                    # If the LSL stream is lost then catch the error and raise it in the observer
                    # TODO: What about stream recovery?
                if stop_event.is_set():
                    break  # Break out of loop on signal to finish function

        # Disposal function for subscription cleanup (called automatically once subscription is over)
        def dispose():
            stop_event.set()  # Signal to stop loop in thread
            # thread.join()  # Wait for thread to complete

        thread = threading.Thread(target=push_chunks_thread)
        thread.start()  # Start thread that forwards LSL stream data to the subscribed observer

        return dispose

    return reactivex.create(push_chunks)
