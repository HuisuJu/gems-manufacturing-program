from __future__ import annotations

import time

from stream.base import Stream, StreamIOError

from .assembler import FrameAssembler
from .frame import Frame
from .fragmenter import FrameFragmenter
from .protocol import (
    DEFAULT_FLOW_CONTROL_TIMEOUT,
    DEFAULT_READ_TIMEOUT,
    DEFAULT_RETRY_COUNT,
    DEFAULT_WRITE_TIMEOUT,
    FRAME_HEADER_SIZE,
    FRAME_MAGIC,
    FRAME_MAX_DATA_SIZE,
    FrameArgumentError,
    FrameError,
    FrameIOError,
    FrameTimeoutError,
    FrameType,
    decode_u16_be,
)


class FrameLink:
    """Packet-level transport on top of the factory frame protocol."""

    def __init__(
        self,
        stream: Stream,
        *,
        packet_capacity: int = 2048,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        write_timeout: float = DEFAULT_WRITE_TIMEOUT,
        flow_control_timeout: float = DEFAULT_FLOW_CONTROL_TIMEOUT,
        retry_count: int = DEFAULT_RETRY_COUNT,
    ) -> None:
        self._stream = stream
        self._packet_capacity = packet_capacity
        self._read_timeout = read_timeout
        self._write_timeout = write_timeout
        self._flow_control_timeout = flow_control_timeout
        self._retry_count = retry_count

        self._pending_rx_frame: Frame | None = None

    @property
    def stream(self) -> Stream:
        """Return the underlying stream."""
        return self._stream

    def send_packet(self, packet: bytes) -> None:
        """Send one packet and wait for ACK/NACK after each frame."""
        fragmenter = FrameFragmenter(packet)

        while not fragmenter.is_finished:
            frame = fragmenter.next_frame()
            sequence = frame.sequence()

            sent = False
            for _ in range(self._retry_count):
                self._write_frame(frame)

                is_ack = self._wait_flow_control(sequence)
                if is_ack:
                    sent = True
                    break

            if not sent:
                raise FrameIOError("failed to send frame after retry limit.")

    def receive_packet(self) -> bytes:
        """Receive one packet, acknowledge its frames, and return packet bytes."""
        assembler = FrameAssembler(packet_capacity=self._packet_capacity)

        while not assembler.is_finished:
            frame = self._load_next_rx_frame(self._read_timeout)

            if frame.type in (FrameType.ACK, FrameType.NACK):
                continue

            sequence = frame.sequence()

            if frame.type == FrameType.CONSECUTIVE and sequence < assembler.expected_sequence:
                self._send_flow_control(True, sequence)
                continue

            if frame.type == FrameType.FIRST and assembler.expected_sequence > 0 and sequence == 0:
                self._send_flow_control(True, sequence)
                continue

            try:
                assembler.process(frame)
            except FrameError:
                self._send_flow_control(False, sequence)
                raise

            self._send_flow_control(True, sequence)

        return assembler.packet

    def _load_next_rx_frame(self, timeout: float) -> Frame:
        """Load the next frame, consuming any pending frame first."""
        if self._pending_rx_frame is not None:
            frame = self._pending_rx_frame
            self._pending_rx_frame = None
            return frame

        return self._read_frame(timeout)

    def _read_frame(self, timeout: float) -> Frame:
        """Read one complete frame from the stream, resynchronizing on magic."""
        deadline = time.monotonic() + timeout
        magic_window = bytearray(b"\x00\x00")

        while True:
            if time.monotonic() >= deadline:
                raise FrameTimeoutError("timed out while waiting for frame magic.")

            magic_window[0] = magic_window[1]
            chunk = self._stream_read_exact(1, deadline - time.monotonic(), allow_partial=False)
            magic_window[1] = chunk[0]

            if decode_u16_be(bytes(magic_window)) == FRAME_MAGIC:
                break

        rest_header = self._stream_read_exact(FRAME_HEADER_SIZE - 2, deadline - time.monotonic())
        header = bytes(magic_window) + rest_header

        payload_size = decode_u16_be(header[3:5])
        if payload_size > FRAME_MAX_DATA_SIZE:
            raise FrameArgumentError("encoded frame payload size exceeds frame maximum.")

        payload = self._stream_read_exact(payload_size, deadline - time.monotonic())
        raw = header + payload
        return Frame.decode(raw)

    def _write_frame(self, frame: Frame) -> None:
        """Write one encoded frame to the stream."""
        raw = frame.encode()

        try:
            ok = self._stream.write(raw)
        except StreamIOError as exc:
            raise FrameIOError("failed to write frame bytes to stream.") from exc

        if not ok:
            raise FrameIOError("stream refused frame write request.")

    def _send_flow_control(self, is_ack: bool, sequence: int) -> None:
        """Send one ACK or NACK control frame."""
        frame = Frame.build_ack(sequence) if is_ack else Frame.build_nack(sequence)
        self._write_frame(frame)

    def _wait_flow_control(self, sequence: int) -> bool:
        """
        Wait for ACK/NACK for the given frame sequence.

        Returns True for ACK and False for NACK.
        """
        deadline = time.monotonic() + self._flow_control_timeout

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()

            frame = self._read_frame(remaining)

            if frame.type not in (FrameType.ACK, FrameType.NACK):
                if self._pending_rx_frame is None:
                    self._pending_rx_frame = frame
                continue

            if frame.sequence() != sequence:
                continue

            return frame.type == FrameType.ACK

        raise FrameTimeoutError("timed out while waiting for flow control response.")

    def _stream_read_exact(
        self,
        size: int,
        timeout: float,
        *,
        allow_partial: bool = True,
    ) -> bytes:
        """Read exactly `size` bytes from the underlying stream before timeout."""
        if size < 0:
            raise FrameArgumentError("read size must not be negative.")

        if size == 0:
            return b""

        deadline = time.monotonic() + max(timeout, 0.0)
        buffer = bytearray()

        while len(buffer) < size:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise FrameTimeoutError("timed out while reading from stream.")

            try:
                chunk = self._stream.read(size - len(buffer), timeout=remaining)
            except StreamIOError as exc:
                raise FrameIOError("failed to read frame bytes from stream.") from exc

            if chunk is None or len(chunk) == 0:
                continue

            buffer.extend(chunk)

            if not allow_partial and len(buffer) > 0:
                break

        if len(buffer) != size:
            raise FrameTimeoutError("failed to read the requested number of bytes.")

        return bytes(buffer)
