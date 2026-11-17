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

## What screen uploads do

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

## V2 keymapping

Keymapping uses a separate, strictly identified VIA interface (interface 1).
Current mappings load automatically on opening the tab and save a full keymap
backup; loading never writes key mappings. All edits remain local until
**Review and apply…** is confirmed. Apply checks for external changes, backs up
before writing, changes only selected keymap words, then verifies every layer.

An unchanged-word write was verified against a complete keymap readback. The
keyboard owner also reports successful changed keymap writes on their device;
this is not exhaustive validation of every assignment or firmware revision.
Restoration and persistence after power cycling remain unverified.
An interrupted write can leave a partial keymap; there is no automatic retry or
rollback. Keep a usable Fn/layer key and close VIA/other configuration tools.
**Load backup…** stages a restore for review; it never writes immediately.
Keymap backups do not include firmware, screen content, lighting or macros.
**Restore defaults** stages a bundled snapshot captured from the configured
keyboard, not manufacturer-certified factory defaults. It requires review and
Apply before writing; no firmware factory-reset command is sent. A separate
first-read recovery baseline is retained and never automatically replaced.
See [the keymapping guide](docs/KEYMAPPING.md) for the full scope and workflow.

## Permissions

Install the supplied narrow udev rule. Do not run the application as root and
do not grant access to every HID device with broad `chmod` rules.
The AppImage cannot install its own system permissions.

## Reporting a problem

Stop after a failed upload and report the exact error, device/firmware
information, distribution, desktop, and application version. Do not repeatedly
retry unknown commands. Review logs before sharing: USB captures can contain
keyboard input and unexpected device/application data.
