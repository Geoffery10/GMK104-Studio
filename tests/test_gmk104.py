import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from protocol import gmk104 as g

ROOT = Path(__file__).resolve().parent


class PacketTests(unittest.TestCase):
    def test_report_checksum_and_padding(self):
        report = g.report(0x21, 2, 56, b"\xf8\x00")
        self.assertEqual(len(report), 64)
        self.assertEqual(report[:8], b"\x04\x53\x01\x21\x02\x38\x00\x00")
        self.assertEqual(report[8:10], b"\xf8\x00")
        self.assertEqual(report[10:], bytes(54))

    def test_reject_invalid_packet_fields(self):
        for args in [(256, 0, 0, b""), (33, 57, 0, bytes(57)),
                     (33, 1, -1, b"x"), (33, 1, 2**24, b"x"),
                     (33, 2, 0, b"x")]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                g.report(*args)

    def test_red_and_blue_encoding(self):
        self.assertEqual(g.rgb565(Image.new("RGB", (1, 1), "red")), b"\xf8\x00")
        self.assertEqual(g.rgb565(Image.new("RGB", (1, 1), "blue")), b"\x00\x1f")

    def test_transparency_is_black_and_square_is_not_stretched(self):
        frame = Image.new("RGBA", (128, 128), (255, 0, 0, 0))
        frame.putpixel((64, 64), (255, 0, 0, 255))
        fitted = g.fit_frame(frame)
        self.assertEqual(fitted.size, (240, 135))
        self.assertEqual(fitted.getpixel((0, 0)), (0, 0, 0))
        self.assertEqual(fitted.getpixel((239, 134)), (0, 0, 0))
        solid = g.fit_frame(Image.new("RGB", (128, 128), "red"))
        self.assertEqual(solid.getbbox(), (52, 0, 187, 135))

    def test_block_layout_and_extra_black_block(self):
        pixels = b"\xf8\x00" * 32400
        blob = g.frame_blob([pixels])
        self.assertEqual(len(blob), 131072)
        self.assertEqual(blob[:64800], pixels)
        self.assertEqual(blob[64800:], bytes(131072 - 64800))

    def test_frame_limits_are_conservative(self):
        for frames in [[], [bytes(64800)] * 3, [b"x"]]:
            with self.subTest(count=len(frames)), self.assertRaises(ValueError):
                g.frame_blob(frames)

    def test_settings_preserve_unknown_bytes(self):
        template = bytearray(range(64))
        template[0], template[3], template[4] = 4, 6, 48
        result = g.settings_report(bytes(template), 2, 500)
        for i in range(64):
            if i not in (1, 2, 42, 51, 52):
                self.assertEqual(result[i], template[i])
        self.assertEqual(result[42], 2)
        self.assertEqual(result[51:53], b"\xf4\x01")
        self.assertEqual(int.from_bytes(result[1:3], "little"), sum(result[3:]))

    def test_settings_limits(self):
        template = g.report(6, 48, 0, bytes(48))
        for count, interval in [(0, 500), (3, 500), (1, 0), (1, 499), (1, 1001)]:
            with self.subTest(count=count, interval=interval), self.assertRaises(ValueError):
                g.settings_report(template, count, interval)


class TransportTests(unittest.TestCase):
    def test_acknowledgment_required_for_every_report(self):
        packet = g.report(1)
        transport = Mock()
        transport.write.return_value = 64
        transport.read.return_value = packet[:8]
        g.send_reports(transport, [packet])
        transport.write.assert_called_once_with(packet)
        transport.read.assert_called_once()

    def test_bad_reply_stops_without_retry(self):
        transport = Mock()
        transport.write.return_value = 64
        transport.read.return_value = bytes(8)
        with self.assertRaises(g.ProtocolError):
            g.send_reports(transport, [g.report(1), g.report(2)])
        self.assertEqual(transport.write.call_count, 1)

    def test_timeout_stops_without_retry(self):
        transport = Mock()
        transport.write.return_value = 64
        transport.read.side_effect = TimeoutError("test timeout")
        with self.assertRaises(TimeoutError):
            g.send_reports(transport, [g.report(1), g.report(2)])
        self.assertEqual(transport.write.call_count, 1)

    def test_short_write_stops(self):
        transport = Mock()
        transport.write.return_value = 12
        with self.assertRaises(g.ProtocolError):
            g.send_reports(transport, [g.report(1)])
        transport.read.assert_not_called()

    def test_discovery_requires_vid_pid_interface_and_exact_descriptor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            interface = root / "usb" / "interface"
            hid = interface / "hid"
            hid.mkdir(parents=True)
            (interface / "bInterfaceNumber").write_text("03\n")
            (hid / "uevent").write_text("HID_ID=0003:0000320F:00005055\n")
            (hid / "report_descriptor").write_bytes(g.SCREEN_DESCRIPTOR)
            entry = root / "class" / "hidraw9"
            entry.mkdir(parents=True)
            (entry / "device").symlink_to(hid, target_is_directory=True)
            self.assertEqual(len(g.discover_devices(root / "class", root / "dev")), 1)
            for attribute, bad in [
                ("bInterfaceNumber", "01\n"),
                ("HID_ID", "0003:00001234:00005055"),
                ("descriptor", b"keyboard"),
            ]:
                with self.subTest(attribute=attribute):
                    if attribute == "bInterfaceNumber":
                        (interface / attribute).write_text(bad)
                    elif attribute == "HID_ID":
                        (hid / "uevent").write_text(f"HID_ID={bad}\n")
                    else:
                        (hid / "report_descriptor").write_bytes(bad)
                    self.assertEqual(g.discover_devices(root / "class", root / "dev"), [])
                    (interface / "bInterfaceNumber").write_text("03\n")
                    (hid / "uevent").write_text("HID_ID=0003:0000320F:00005055\n")
                    (hid / "report_descriptor").write_bytes(g.SCREEN_DESCRIPTOR)

    def test_real_transport_timeout_does_not_read(self):
        transport = g.HidrawTransport(g.Device(Path("/unused"), Path("/unused")))
        transport.fd = 99
        with patch.object(g.select, "select", return_value=([], [], [])), patch.object(g.os, "read") as read:
            with self.assertRaises(TimeoutError):
                transport.read()
            read.assert_not_called()


class CliSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        capture = Path(self.temp.name) / "settings.json"
        settings = bytes.fromhex(json.loads((ROOT / "fixtures/uploads.json").read_text())[0]["prefix"][1])
        capture.write_text(json.dumps([{"_source": {"layers": {
            "usb": {"usb.endpoint_address": "0x05", "usb.urb_type": "'S'",
                    "usb.bus_id": "1", "usb.data_len": "64"},
            "frame": {"frame.encap_type": "115"},
            "frame_raw": [(bytes(64) + settings).hex()],
        }}}]))
        self.args = [str(ROOT / "artwork" / "01-red.gif"), "--settings-from", str(capture)]

    def test_default_is_offline_and_does_not_discover_or_open_device(self):
        with patch.object(g, "discover_devices") as discover, patch.object(g.os, "open") as open_device:
            self.assertEqual(g.main(self.args), 0)
            discover.assert_not_called()
            open_device.assert_not_called()

    def test_noninteractive_upload_cannot_open_device(self):
        device = g.Device(Path("/dev/hidraw9"), Path("/sys/fake"))
        with patch.object(g, "discover_devices", return_value=[device]), \
                patch.object(g.sys.stdin, "isatty", return_value=False), \
                patch.object(g.os, "open") as open_device:
            with self.assertRaises(g.ProtocolError):
                g.main([self.args[0], "--upload"])
            open_device.assert_not_called()

    def test_output_will_not_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "existing.bin"
            output.write_bytes(b"user data")
            with self.assertRaises(FileExistsError):
                g.main(self.args + ["--output", str(output)])
            self.assertEqual(output.read_bytes(), b"user data")


class CaptureRegressionTests(unittest.TestCase):
    def test_all_five_captures_match_generated_pixels_and_framing(self):
        cases = json.loads((ROOT / "fixtures/uploads.json").read_text())
        for case in cases:
            with self.subTest(label=case["name"]):
                prefix = [bytes.fromhex(value) for value in case["prefix"]]
                template = g.capture_settings(prefix)
                frames, durations = g.load_frames(ROOT / "artwork" / (case["name"] + ".gif"))
                interval = case["interval"]
                generated = list(g.upload_reports(frames, template, interval))
                self.assertEqual(len(generated), case["report_count"])
                self.assertEqual(generated[:5], prefix)
                self.assertEqual(generated[-1], bytes.fromhex(case["suffix"]))
                self.assertEqual([hashlib.sha256(frame).hexdigest() for frame in frames],
                                 case["frame_sha256"])
                data_packets = []
                for packet in generated:
                    self.assertEqual(int.from_bytes(packet[1:3], "little"), sum(packet[3:]))
                    if packet[3] == 33:
                        self.assertEqual(int.from_bytes(packet[5:8], "little"), len(data_packets) * 56)
                        data_packets.append(packet)
                self.assertEqual(sum(packet[4] for packet in data_packets), case["stream_bytes"])
                self.assertEqual(data_packets[-1][4], case["last_chunk_length"])

    def test_template_without_settings_is_rejected(self):
        with self.assertRaises(ValueError):
            g.capture_settings([g.report(1)])


if __name__ == "__main__":
    unittest.main()
