import threading
from typing import Dict

from schemas.mesh_packet import MeshPacketSchema


class VirtualDevice:
    def __init__(self, device_id: str, has_internet: bool):
        self.device_id = device_id
        self.has_internet = has_internet
        self._lock = threading.Lock()
        self._held_packets: Dict[str, MeshPacketSchema] = {}

    def hold(self, packet: MeshPacketSchema) -> None:
        with self._lock:
            self._held_packets.setdefault(packet.packetId, packet)

    def get_held_packets(self) -> list[MeshPacketSchema]:
        with self._lock:
            return list(self._held_packets.values())

    def holds(self, packet_id: str) -> bool:
        with self._lock:
            return packet_id in self._held_packets

    def packet_count(self) -> int:
        with self._lock:
            return len(self._held_packets)

    def clear(self) -> None:
        with self._lock:
            self._held_packets.clear()
