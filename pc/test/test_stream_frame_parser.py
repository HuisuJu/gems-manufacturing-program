from stream.frame_parser import (
    FRAME_TYPE_ACK,
    FRAME_TYPE_CONSECUTIVE,
    FRAME_TYPE_FIRST,
    FRAME_TYPE_SINGLE,
    PacketAssembler,
    PacketFragmenter,
    StreamFrameParser,
    build_control_frame,
    control_sequence_from_frame,
    decode_frame,
    encode_frame,
)


def test_encode_decode_frame_big_endian_header():
    payload = bytes(range(20))
    raw = encode_frame(FRAME_TYPE_SINGLE, payload)

    # size=20 => 0x0014, big-endian in header[3:5]
    assert raw[3] == 0x00
    assert raw[4] == 0x14

    decoded = decode_frame(raw)
    assert decoded.frame_type == FRAME_TYPE_SINGLE
    assert decoded.size == len(payload)
    assert decoded.payload == payload


def test_stream_parser_handles_chunked_input_and_magic_sync():
    payload = b"hello-frame"
    frame = encode_frame(FRAME_TYPE_SINGLE, payload)

    parser = StreamFrameParser()
    out = []
    out.extend(parser.feed(b"\x00\x11\x22"))
    out.extend(parser.feed(frame[:4]))
    out.extend(parser.feed(frame[4:]))

    assert len(out) == 1
    assert out[0].payload == payload


def test_fragmenter_and_assembler_roundtrip_with_duplicate_consecutive():
    packet = bytes((i % 251 for i in range(900)))

    fragmenter = PacketFragmenter(packet)
    assembler = PacketAssembler()

    done_packet = None
    while not fragmenter.done():
        raw, _seq = fragmenter.next_frame()
        frame = decode_frame(raw)

        status, maybe_packet, seq = assembler.process(frame)
        assert status in ("ok", "done")

        # inject one duplicate on first consecutive frame
        if frame.frame_type == FRAME_TYPE_CONSECUTIVE and seq == 1:
            d_status, d_pkt, d_seq = assembler.process(frame)
            assert d_status == "duplicate"
            assert d_pkt is None
            assert d_seq == 1

        if status == "done":
            done_packet = maybe_packet

    assert done_packet == packet


def test_control_frame_roundtrip():
    raw = build_control_frame(True, 0x7A)
    frame = decode_frame(raw)
    assert frame.frame_type == FRAME_TYPE_ACK
    assert control_sequence_from_frame(frame) == 0x7A
