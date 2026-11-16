import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from protocol import gmk104 as g

ROOT = Path(__file__).resolve().parent


def startup_exchanges():
    fixture = json.loads((ROOT / "fixtures/readback.json").read_text())
    return [(bytes.fromhex(item["request"]), bytes.fromhex(item["reply"]))
            for item in fixture["exchanges"]]


class ReadbackTests(unittest.TestCase):
    def setUp(self):
        self.exchanges = [(request, reply) for request, reply in startup_exchanges() if request[3] == 5]
        self.transport = Mock()
        self.transport.write.return_value = 64
        self.transport.read.side_effect = [reply for _, reply in self.exchanges]

    def test_read_requests_exactly_match_startup_capture(self):
        snapshot = g.read_current_settings(self.transport)
        sent = [call.args[0] for call in self.transport.write.call_args_list]
        self.assertEqual(sent, [request for request, _ in self.exchanges])
        self.assertEqual(len(snapshot.payload), 48)
        expected = b"".join(reply[4:8] for _, reply in self.exchanges[1:])
        self.assertEqual(snapshot.payload, expected)
        self.assertEqual(snapshot.report, g.report(6, 48, 0, expected))

    def test_only_frame_count_interval_and_checksum_change(self):
        snapshot = g.read_current_settings(self.transport)
        new = g.settings_report(snapshot.report, 1, 500)
        self.assertEqual(new[42], 1)
        self.assertEqual(new[51:53], b"\xf4\x01")
        for index in range(64):
            if index not in (1, 2, 42, 51, 52):
                self.assertEqual(new[index], snapshot.report[index])

    def test_wrong_header_stops_read_without_retry(self):
        self.transport.read.side_effect = [b"\x04\xff\x00\x05" + bytes(4)]
        with self.assertRaises(g.ProtocolError):
            g.read_current_settings(self.transport)
        self.assertEqual(self.transport.write.call_count, 1)

    def test_truncated_reply_stops(self):
        self.transport.read.side_effect = [bytes(4)]
        with self.assertRaises(g.ProtocolError):
            g.read_current_settings(self.transport)

    def test_short_read_request_does_not_wait_for_reply(self):
        self.transport.write.return_value = 12
        with self.assertRaises(g.ProtocolError):
            g.read_current_settings(self.transport)
        self.transport.read.assert_not_called()

    def test_windows_startup_preserves_settings_except_clock_and_checksum(self):
        snapshot = g.read_current_settings(self.transport)
        written = next(request for request, _ in startup_exchanges() if request[3] == 6)
        for index in range(64):
            if index not in (1, 2) and index not in range(43, 50):
                self.assertEqual(snapshot.report[index], written[index])

    def test_unsupported_profile_is_not_overwritten(self):
        response = bytearray(self.exchanges[0][1])
        response[4] = 1
        self.transport.read.side_effect = [bytes(response)]
        with self.assertRaises(g.ProtocolError):
            g.read_current_settings(self.transport)
        self.assertEqual(self.transport.write.call_count, 1)

    def test_read_timeout_does_not_attempt_configuration_write(self):
        self.transport.read.side_effect = TimeoutError("timeout")
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(TimeoutError):
            g.upload_with_backup(self.transport, [bytes(64800)], 500,
                                 Path(directory), g.Device(Path("/unused"), Path("/unused")))
        self.assertTrue(all(call.args[0][3] == 5 for call in self.transport.write.call_args_list))

    def test_backup_contains_raw_settings_and_full_read_transcript(self):
        snapshot = g.read_current_settings(self.transport)
        with tempfile.TemporaryDirectory() as directory:
            path = g.backup_settings(snapshot, Path(directory), g.Device(Path("/unused"), Path("/unused")))
            data = json.loads(path.read_text())
            self.assertEqual(bytes.fromhex(data["settings_hex"]), snapshot.payload)
            self.assertEqual(bytes.fromhex(data["write_report_hex"]), snapshot.report)
            self.assertEqual(len(data["exchanges"]), 13)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_backup_failure_prevents_all_configuration_writes(self):
        with patch.object(g, "backup_settings", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                g.upload_with_backup(self.transport, [bytes(64800)], 500,
                                     Path("/unused"), g.Device(Path("/unused"), Path("/unused")))
        self.assertEqual(self.transport.write.call_count, 13)
        self.assertTrue(all(call.args[0][3] == 5 for call in self.transport.write.call_args_list))

    def test_successful_upload_uses_live_settings_after_backup(self):
        device = g.Device(Path("/unused"), Path("/unused"))
        expected = g.read_current_settings(self.transport)
        frames = [b"\xf8\x00" * 32400]
        reports = list(g.upload_reports(frames, expected.report, 500))
        self.transport.reset_mock()
        self.transport.read.side_effect = [reply for _, reply in self.exchanges] + [r[:8] for r in reports]
        with tempfile.TemporaryDirectory() as directory:
            path = g.upload_with_backup(self.transport, frames, 500, Path(directory), device)
            self.assertTrue(path.exists())
        sent = [call.args[0] for call in self.transport.write.call_args_list]
        self.assertEqual(sent[13:], reports)


if __name__ == "__main__":
    unittest.main()
