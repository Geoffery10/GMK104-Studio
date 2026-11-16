# Device safety and responsibility

This is an independent, community-developed tool for the ZUOYA GMK104. It is
not affiliated with, endorsed by, or supported by the keyboard manufacturer.
It was developed by observing USB traffic and testing a limited configuration,
not from an official protocol specification.

**Use at your own risk.** The software is supplied as-is under the MIT License.
To the extent permitted by applicable law, Geoffery10 and all other contributors
accept no responsibility or liability for damaged or unusable devices, lost
settings or artwork, data loss, interrupted uploads, or other direct or indirect
losses resulting from its use. Mandatory legal rights are not excluded.

Safety checks reduce risk; they cannot guarantee a damage-free upload.

## Tested scope in v1.0

- ZUOYA GMK104, USB VID/PID `320f:5055`, observed screen interface 3.
- Wired USB mode, Custom1, one or two frames, global intervals 500–1000 ms.
- Hardware validation on one Linux system. Different firmware revisions or
  devices with the same USB identifiers may behave differently.

Do not try this with other keyboard models, flash firmware, remove the USB cable
during an upload, or run the Windows configuration tool concurrently.
The application does not implement firmware updating.

## What the application does

1. Checks device identity, interface number, and exact HID report descriptor.
2. Reads the current 48-byte settings record.
3. Saves a private, timestamped settings backup before writing.
4. Changes only the identified frame-count and interval fields and checksum.
5. Sends image data and requires an acknowledgment for every report.
6. Stops on a timeout, short write, bad reply, or failed settings backup.

It never silently falls back to an old captured settings profile, retries
state-changing commands, or automatically restores settings.

Backups contain **settings only**, not firmware or the current animation.
They are useful evidence, not a guaranteed recovery mechanism.

Clicking **Upload to keyboard** starts immediately. The GUI has no additional
confirmation dialog. Errors are shown, and settings backups remain mandatory.
The CLI requires explicit confirmation for uploads.

## Permissions

Install the supplied narrow udev rule. Do not run the application as root and
do not grant access to every HID device with broad `chmod` rules.
The AppImage cannot install its own system permissions.

## Reporting a problem

Stop after a failed upload and report the exact error, device/firmware
information, distribution, desktop, and application version. Do not repeatedly
retry unknown commands. Review logs before sharing: USB captures can contain
keyboard input and unexpected device/application data.
