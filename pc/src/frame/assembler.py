from __future__ import annotations

from .frame import Frame
from .protocol import (
    FrameArgumentError,
    FrameOverflowError,
    FrameSequenceError,
    FrameType,
    decode_u32_be,
)


class FrameAssembler:
    """Reassemble one packet from one or more transport frames."""

    def __init__(self, packet_capacity: int = 2048) -> None:
        if packet_capacity <= 0:
            raise FrameArgumentError("packet_capacity must be positive.")

        self._packet_capacity = packet_capacity
        self.reset()

    @property
    def packet_capacity(self) -> int:
        """Return the packet capacity configured for this assembler."""
        return self._packet_capacity

    @property
    def expected_sequence(self) -> int:
        """Return the next expected sequence number."""
        return self._expected_sequence

    @property
    def total_size(self) -> int:
        """Return the total expected packet size."""
        return self._total_size

    @property
    def packet_size(self) -> int:
        """Return the number of assembled packet bytes."""
        return len(self._buffer)

    @property
    def is_finished(self) -> bool:
        """Return whether packet assembly is complete."""
        return self._is_finished

    @property
    def packet(self) -> bytes:
        """Return the reassembled packet bytes."""
        if not self._is_finished:
            raise FrameArgumentError("packet assembly is not finished.")
        return bytes(self._buffer)

    def reset(self) -> None:
        """Reset assembler state for a new packet."""
        self._buffer = bytearray()
        self._expected_sequence = 0
        self._total_size = 0
        self._is_finished = False

    def process(self, frame: Frame) -> None:
        """Consume one frame and update packet assembly state."""
        if self._is_finished:
            raise FrameArgumentError("packet assembly is already finished.")

        if frame.type == FrameType.SINGLE:
            data = frame.payload
            self._ensure_capacity(len(data))
            self._buffer[:] = data
            self._expected_sequence = 0xFF
            self._total_size = len(data)
            self._is_finished = True
            return

        if frame.type == FrameType.FIRST:
            self._process_first(frame)
            return

        if frame.type == FrameType.CONSECUTIVE:
            self._process_consecutive(frame)
            return

        raise FrameArgumentError(f"unsupported frame type for assembly: {frame.type!r}")

    def _process_first(self, frame: Frame) -> None:
        payload = frame.payload

        if len(payload) < 5:
            raise FrameArgumentError("FIRST frame payload is too short.")

        sequence = payload[4]
        if sequence != 0:
            raise FrameSequenceError("FIRST frame sequence must be 0.")

        total_size = decode_u32_be(payload[0:4])
        chunk = payload[5:]

        self._ensure_capacity(total_size)

        if len(chunk) > total_size:
            raise FrameOverflowError("FIRST frame data exceeds total packet size.")

        self._buffer[:] = chunk
        self._total_size = total_size
        self._expected_sequence = 1

        if len(self._buffer) == self._total_size:
            self._is_finished = True

    def _process_consecutive(self, frame: Frame) -> None:
        payload = frame.payload

        if len(payload) < 1:
            raise FrameArgumentError("CONSECUTIVE frame payload is too short.")

        if self._total_size == 0:
            raise FrameSequenceError("CONSECUTIVE frame arrived before FIRST frame.")

        sequence = payload[0]
        if sequence != self._expected_sequence:
            raise FrameSequenceError(
                f"unexpected consecutive sequence: expected {self._expected_sequence}, got {sequence}."
            )

        chunk = payload[1:]
        next_size = len(self._buffer) + len(chunk)

        if next_size > self._packet_capacity:
            raise FrameOverflowError("assembled packet exceeds packet capacity.")

        if next_size > self._total_size:
            raise FrameOverflowError("assembled packet exceeds declared total size.")

        self._buffer.extend(chunk)
        self._expected_sequence += 1

        if len(self._buffer) == self._total_size:
            self._is_finished = True

    def _ensure_capacity(self, total_size: int) -> None:
        if total_size > self._packet_capacity:
            raise FrameOverflowError("declared packet size exceeds packet capacity.")
