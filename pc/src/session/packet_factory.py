# packet_factory.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Type

from .packet import PacketType, PacketBuilder, PacketParser
from .packet_builders import (
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
        PacketType.PC_HELLO: _BuilderSpec(PcHelloBuilder),
        PacketType.PC_ALERT: _BuilderSpec(PcAlertBuilder),
        PacketType.PC_BYE: _BuilderSpec(PcFinishBuilder),
        PacketType.MESSAGE: _BuilderSpec(InformationBuilder),
    }

    _PARSERS: dict[PacketType, _ParserSpec] = {
        PacketType.DEV_HELLO: _ParserSpec(DevHelloParser),
        PacketType.DEV_ALERT: _ParserSpec(DevAlertParser),
        PacketType.MESSAGE: _ParserSpec(InformationParser),
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

        if len(packet) < 2:
            raise ValueError("packet too short to determine type")

        raw_type = packet[1]
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
