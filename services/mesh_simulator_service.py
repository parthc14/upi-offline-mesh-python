import threading
import logging
from dataclasses import dataclass
from typing import Dict, List

from services.virtual_device import VirtualDevice
from schemas.mesh_packet import MeshPacketSchema

logger = logging.getLogger(__name__)


@dataclass
class GossipResult:
    transfers: int
    device_counts: Dict[str, int]


@dataclass
class BridgeUpload:
    bridge_node_id: str
    packet: MeshPacketSchema


class MeshSimulatorService:
    def __init__(self):
        self._lock = threading.Lock()
        self._devices: Dict[str, VirtualDevice] = {}
        self._seed_default_devices()

    def _seed_default_devices(self):
        for device_id, has_internet in [
            ("phone-alice", False),
            ("phone-stranger1", False),
            ("phone-stranger2", False),
            ("phone-stranger3", False),
            ("phone-bridge", True),
        ]:
            self._devices[device_id] = VirtualDevice(device_id, has_internet)

    def get_devices(self) -> list[VirtualDevice]:
        with self._lock:
            return list(self._devices.values())

    def get_device(self, device_id: str) -> VirtualDevice:
        with self._lock:
            return self._devices.get(device_id)

    def inject(self, sender_device_id: str, packet: MeshPacketSchema) -> None:
        device = self.get_device(sender_device_id)
        if device is None:
            raise ValueError(f"Unknown device: {sender_device_id}")
        device.hold(packet)
        logger.info(
            "Packet %s injected at %s (TTL=%d)",
            packet.packetId[:8],
            sender_device_id,
            packet.ttl,
        )

    def gossip_once(self) -> GossipResult:
        transfers = 0
        device_list = self.get_devices()

        snapshot: Dict[str, List[MeshPacketSchema]] = {
            d.device_id: d.get_held_packets() for d in device_list
        }

        for src in device_list:
            for pkt in snapshot[src.device_id]:
                if pkt.ttl <= 0:
                    continue
                for dst in device_list:
                    if dst is src:
                        continue
                    if dst.holds(pkt.packetId):
                        continue
                    copy = MeshPacketSchema(
                        packetId=pkt.packetId,
                        ttl=pkt.ttl - 1,
                        createdAt=pkt.createdAt,
                        ciphertext=pkt.ciphertext,
                    )
                    dst.hold(copy)
                    transfers += 1

        logger.info("Gossip round complete: %d packet transfers", transfers)
        return GossipResult(transfers=transfers, device_counts=self.snapshot_map())

    def snapshot_map(self) -> Dict[str, int]:
        return {d.device_id: d.packet_count() for d in self.get_devices()}

    def collect_bridge_uploads(self) -> List[BridgeUpload]:
        return [
            BridgeUpload(bridge_node_id=d.device_id, packet=pkt)
            for d in self.get_devices()
            if d.has_internet
            for pkt in d.get_held_packets()
        ]

    def reset_mesh(self) -> None:
        for d in self.get_devices():
            d.clear()


mesh_simulator_service = MeshSimulatorService()
