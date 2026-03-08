# packet_factory.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Type

from .packet import PacketType, MAGIC_BYTES, PacketBuilder, PacketParser
from .packet_builders import (
    PcAdvBuilder,
    PcHelloBuilder,
    PcAlertBuilder,
    PcFinishBuilder,
    InformationBuilder,
)
from .packet_parsers import (
    DevHelloParser,
    DevAlertParser,
    InformationParser,
)


@dataclass(frozen=True, slots=True)
class _BuilderSpec:
    cls: Type[PacketBuilder]


@dataclass(frozen=True, slots=True)
class _ParserSpec:
    cls: Type[PacketParser]


class PacketFactory:
    _BUILDERS: dict[PacketType, _BuilderSpec] = {
        PacketType.PC_ADV: _BuilderSpec(PcAdvBuilder),
        PacketType.PC_HELLO: _BuilderSpec(PcHelloBuilder),
        PacketType.PC_ALERT: _BuilderSpec(PcAlertBuilder),
        PacketType.PC_FINISH: _BuilderSpec(PcFinishBuilder),
        PacketType.INFORMATION: _BuilderSpec(InformationBuilder),
    }

    _PARSERS: dict[PacketType, _ParserSpec] = {
        PacketType.DEV_HELLO: _ParserSpec(DevHelloParser),
        PacketType.DEV_ALERT: _ParserSpec(DevAlertParser),
        PacketType.INFORMATION: _ParserSpec(InformationParser),
    }

    @classmethod
    def build(cls, pkt_type: PacketType, **kwargs: Any) -> PacketBuilder:
        spec = cls._BUILDERS.get(pkt_type)
        if spec is None:
            raise ValueError(f"no builder registered for {pkt_type.name}")
        return spec.cls(**kwargs)  # type: ignore[misc]

    @classmethod
    def parser(cls, pkt_type: PacketType) -> PacketParser:
        spec = cls._PARSERS.get(pkt_type)
        if spec is None:
            raise ValueError(f"no parser registered for {pkt_type.name}")
        return spec.cls()

    @classmethod
    def parse(cls, packet: bytes) -> PacketParser:
        if not isinstance(packet, (bytes, bytearray, memoryview)):
            raise TypeError("packet must be bytes-like")

        packet = bytes(packet)

        if len(packet) < 3:
            raise ValueError("packet too short to determine type")

        if packet[0:2] != MAGIC_BYTES:
            raise ValueError("bad magic")

        raw_type = packet[2]
        try:
            pkt_type = PacketType(raw_type)
        except ValueError:
            pkt_type = PacketType.UNKNOWN

        spec = cls._PARSERS.get(pkt_type)
        if spec is None:
            raise ValueError(f"no parser registered for {pkt_type.name}")

        parser = spec.cls()
        parser.parse(packet)
        return parser
