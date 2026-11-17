"""Offline VIA tests: no real HID devices are opened."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from protocol import via
from protocol.gmk104 import Device, ProtocolError


class FakeKeyboard:
    def __init__(self):
        self.data = bytearray((i % 256 for i in range(via.MAP_SIZE)))
        self.packets = []
        self.version = via.PROTOCOL_VERSION
        self.layers = 4
        self.corrupt = False
        self.fail_write = False

    def exchange(self, packet):
        self.packets.append(packet)
        reply = bytearray(packet)
        if packet[0] == 1:
            reply[1:3] = self.version.to_bytes(2, "big")
        elif packet[0] == 0x11:
            reply[1] = self.layers
        elif packet[0] in (0x12, 0x13):
            offset = int.from_bytes(packet[1:3], "big")
            size = packet[3]
            if packet[0] == 0x12:
                reply[4:4 + size] = self.data[offset:offset + size]
                if self.corrupt:
                    reply[1] ^= 1
            else:
                if self.fail_write:
                    raise TimeoutError("simulated lost acknowledgment")
                self.data[offset:offset + size] = packet[4:4 + size]
        return bytes(reply)

    @property
    def writes(self):
        return [p for p in self.packets if p[0] == 0x13]


class ViaTests(unittest.TestCase):
    def setUp(self):
        self.keyboard = FakeKeyboard()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.device = Device(Path("/unused"), Path("/unused/sysfs"))

    def tearDown(self):
        self.temp.cleanup()

    def test_full_read_preserves_every_word_without_writes(self):
        snapshot = via.read_keymap(self.keyboard)
        self.assertEqual(snapshot.data, bytes(self.keyboard.data))
        self.assertEqual(snapshot.keycode(0, 0, 1), 0x0203)
        self.assertEqual(self.keyboard.writes, [])

    def test_unknown_version_and_layer_count_fail_closed(self):
        self.keyboard.version = 9
        with self.assertRaises(ProtocolError):
            via.read_keymap(self.keyboard)
        self.keyboard.version = via.PROTOCOL_VERSION
        self.keyboard.layers = 3
        with self.assertRaises(ProtocolError):
            via.read_keymap(self.keyboard)
        self.assertEqual(self.keyboard.writes, [])

    def test_mismatched_buffer_reply_stops(self):
        self.keyboard.corrupt = True
        with self.assertRaises(ProtocolError):
            via.read_keymap(self.keyboard)

    def test_backup_roundtrip_private_and_tamper_checked(self):
        snapshot = via.read_keymap(self.keyboard)
        path = via.backup_keymap(snapshot, self.root, self.device)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(via.load_backup(path), snapshot)
        record = json.loads(path.read_text())
        record["keymap_hex"] = "00" * via.MAP_SIZE
        path.write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            via.load_backup(path)

    def test_apply_only_changed_word_and_verify(self):
        original = via.read_keymap(self.keyboard)
        data = bytearray(original.data)
        data[92:94] = b"\0\x04"
        desired = via.Snapshot(bytes(data))
        path = via.apply_keymap(self.keyboard, original, desired, self.root, self.device)
        self.assertEqual(via.load_backup(path), original)
        self.assertEqual(bytes(self.keyboard.data), desired.data)
        self.assertEqual(len(self.keyboard.writes), 1)
        self.assertEqual(self.keyboard.writes[0][1:6], b"\0\x5c\x02\0\x04")

    def test_stale_snapshot_prevents_writes(self):
        original = via.read_keymap(self.keyboard)
        self.keyboard.data[0] ^= 1
        with self.assertRaisesRegex(ProtocolError, "changed since Read"):
            via.apply_keymap(self.keyboard, original, original, self.root, self.device)
        self.assertEqual(self.keyboard.writes, [])

    def test_backup_failure_prevents_writes(self):
        original = via.read_keymap(self.keyboard)
        with patch.object(via, "backup_keymap", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                via.apply_keymap(self.keyboard, original, original, self.root, self.device)
        self.assertEqual(self.keyboard.writes, [])

    def test_timeout_stops_without_retry_and_reports_backup(self):
        original = via.read_keymap(self.keyboard)
        desired = via.Snapshot(b"\0" * via.MAP_SIZE)
        self.keyboard.fail_write = True
        with self.assertRaisesRegex(ProtocolError, "Backup:"):
            via.apply_keymap(self.keyboard, original, desired, self.root, self.device)
        self.assertEqual(len(self.keyboard.writes), 1)
        self.assertEqual(len(list(self.root.glob("keymap-*.json"))), 1)

    def test_unchanged_write_test_writes_one_identical_word(self):
        before = bytes(self.keyboard.data)
        path = via.confirm_unchanged_write(self.keyboard, self.root, self.device)
        self.assertEqual(bytes(self.keyboard.data), before)
        self.assertEqual(via.load_backup(path).data, before)
        self.assertEqual(len(self.keyboard.writes), 1)

    def test_offsets_and_snapshot_bounds(self):
        for args in ((4, 0, 0), (0, 8, 0), (0, 0, 15), (-1, 0, 0)):
            with self.assertRaises(ValueError):
                via.key_offset(*args)
        with self.assertRaises(ValueError):
            via.Snapshot(bytes(10))
        with self.assertRaises(ValueError):
            via._write_word(self.keyboard, 1, b"\0\0")
        self.assertEqual(self.keyboard.packets, [])

    def test_full_verification_failure_reports_backup_without_rollback(self):
        original = via.read_keymap(self.keyboard)
        desired = via.Snapshot(b"\0" * via.MAP_SIZE)
        with patch.object(via, "read_keymap", side_effect=[original, original]):
            with self.assertRaisesRegex(ProtocolError, "verification failed.*Backup:"):
                via.apply_keymap(self.keyboard, original, desired, self.root, self.device)
        self.assertEqual(len(self.keyboard.writes), via.MAP_SIZE // 2)
        self.assertEqual(bytes(self.keyboard.data), desired.data)

    def test_bad_write_ack_stops(self):
        with patch.object(self.keyboard, "exchange", return_value=b"\x13" + bytes(31)):
            with self.assertRaisesRegex(ProtocolError, "acknowledgment"):
                via._write_word(self.keyboard, 92, b"\0\x04")

    def test_invalid_backup_shape_is_rejected(self):
        path = self.root / "invalid.json"
        for text in ("[]", "{}", "x" * 16385):
            path.write_text(text)
            with self.assertRaises(ValueError):
                via.load_backup(path)

    def test_transport_rejects_forbidden_commands_and_unsafe_buffer_writes(self):
        transport = via.HidrawTransport(self.device)
        with patch.object(via.os, "write") as write:
            for data in (b"\x0b", b"\x05", b"\x15", b"\x13\0\0\x1c",
                         b"\x13\0\x01\x02", b"\x13\xff\xff\x02"):
                with self.assertRaises(ValueError):
                    transport.exchange(data.ljust(32, b"\0"))
            write.assert_not_called()

    def test_transport_adds_zero_report_id_and_checks_reply(self):
        transport = via.HidrawTransport(self.device)
        transport.fd = 99
        packet = b"\x01" + bytes(31)
        with patch.object(via.select, "select", return_value=([99], [99], [])), \
                patch.object(via.os, "write", return_value=33) as write, \
                patch.object(via.os, "read", return_value=packet):
            self.assertEqual(transport.exchange(packet), packet)
            write.assert_called_once_with(99, b"\0" + packet)

    def test_transport_short_write_and_timeout_never_read_or_retry(self):
        transport = via.HidrawTransport(self.device)
        transport.fd = 99
        with patch.object(via.select, "select", return_value=([99], [99], [])), \
                patch.object(via.os, "write", return_value=32) as write, \
                patch.object(via.os, "read") as read:
            with self.assertRaises(ProtocolError):
                transport.exchange(b"\x01" + bytes(31))
            write.assert_called_once()
            read.assert_not_called()
        with patch.object(via.select, "select", side_effect=[([], [99], []), ([], [], [])]), \
                patch.object(via.os, "write", return_value=33), \
                patch.object(via.os, "read") as read:
            with self.assertRaises(TimeoutError):
                transport.exchange(b"\x01" + bytes(31))
            read.assert_not_called()

    def test_identity_change_prevents_open(self):
        with patch.object(via, "discover_devices", return_value=[]), \
                patch.object(via.os, "open") as open_device:
            with self.assertRaises(ProtocolError):
                with via.HidrawTransport(self.device):
                    pass
            open_device.assert_not_called()

    def test_baseline_keeps_first_snapshot_across_reads_and_apply(self):
        original = via.read_keymap(self.keyboard)
        path = via.ensure_baseline(original, self.root, self.device)
        saved = path.read_bytes()
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        desired = via.Snapshot(b"\0" * via.MAP_SIZE)
        via.apply_keymap(self.keyboard, original, desired, self.root, self.device)
        via.ensure_baseline(desired, self.root, self.device)
        self.assertEqual(via.load_backup(path), original)
        self.assertEqual(path.read_bytes(), saved)

    def test_corrupt_baseline_is_not_replaced_and_blocks_apply(self):
        original = via.read_keymap(self.keyboard)
        path = via.ensure_baseline(original, self.root, self.device)
        path.write_text("corrupt baseline")
        with self.assertRaises(ValueError):
            via.apply_keymap(self.keyboard, original, via.Snapshot(bytes(via.MAP_SIZE)),
                             self.root, self.device)
        self.assertEqual(path.read_text(), "corrupt baseline")
        self.assertEqual(self.keyboard.writes, [])

    def test_failed_baseline_publish_does_not_leave_partial_baseline(self):
        original = via.read_keymap(self.keyboard)
        with patch.object(via.os, "link", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                via.ensure_baseline(original, self.root, self.device)
        self.assertFalse(via.baseline_path(self.root).exists())
        self.assertEqual(self.keyboard.writes, [])
        self.assertEqual(via.load_backup(via.ensure_baseline(original, self.root, self.device)), original)

    def test_first_apply_also_saves_baseline_before_any_change(self):
        original = via.read_keymap(self.keyboard)
        via.apply_keymap(self.keyboard, original, via.Snapshot(bytes(via.MAP_SIZE)),
                         self.root, self.device)
        self.assertEqual(via.load_backup(via.baseline_path(self.root)), original)


if __name__ == "__main__":
    unittest.main()
