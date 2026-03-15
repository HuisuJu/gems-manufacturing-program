from __future__ import annotations

from .frame import Frame
from .protocol import (
    FRAME_MAX_DATA_SIZE,
    FrameArgumentError,
    max_consecutive_frame_data_size,
    max_first_frame_data_size,
)


class FrameFragmenter:
    """Split one packet into one or more transport frames."""

    def __init__(self, packet: bytes) -> None:
        self._packet = bytes(packet)

        if len(self._packet) == 0:
            raise FrameArgumentError("packet must not be empty.")

        self._packet_size = len(self._packet)
        self._index = 0
        self._sequence = 0
        self._need_fragmentation = self._packet_size > FRAME_MAX_DATA_SIZE
        self._is_finished = False

    @property
    def packet(self) -> bytes:
        """Return the original packet bytes."""
        return self._packet

    @property
    def packet_size(self) -> int:
        """Return the original packet size."""
        return self._packet_size

    @property
    def need_fragmentation(self) -> bool:
        """Return whether the packet requires multiple frames."""
        return self._need_fragmentation

    @property
    def is_finished(self) -> bool:
        """Return whether all frames have been generated."""
        return self._is_finished

    def next_frame(self) -> Frame:
        """Generate and return the next frame."""
        if self._is_finished:
            raise FrameArgumentError("fragmentation is already finished.")

        if self._index >= self._packet_size:
            self._is_finished = True
            raise FrameArgumentError("packet offset is out of range.")

        if not self._need_fragmentation:
            frame = Frame.build_single(self._packet)
            self._index = self._packet_size
            self._is_finished = True
            return frame

        if self._sequence == 0:
            max_chunk_size = max_first_frame_data_size()
            chunk = self._packet[:max_chunk_size]

            frame = Frame.build_first(
                total_size=self._packet_size,
                sequence=0,
                chunk=chunk,
            )

            self._index += len(chunk)
            self._sequence += 1
            return frame

        max_chunk_size = max_consecutive_frame_data_size()
        remaining = self._packet_size - self._index
        chunk_size = min(remaining, max_chunk_size)
        chunk = self._packet[self._index : self._index + chunk_size]

        frame = Frame.build_consecutive(sequence=self._sequence, chunk=chunk)

        self._index += len(chunk)
        self._sequence += 1

        if self._index >= self._packet_size:
            self._is_finished = True

        return frame
