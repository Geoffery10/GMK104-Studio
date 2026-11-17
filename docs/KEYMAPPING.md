# V2 keymapping

Run the V2 AppImage or the source app with `python -m gmk104_app`. The **Screen** tab is unchanged;
**Keymap** adds an independent wired VIA editor.

## Workflow

1. Use wired USB mode. Close usevia.app and other keyboard configuration tools.
2. Open **Keymap**. Current mappings load automatically and a
   private backup is saved. If disconnected, loading waits for a connection.
   **Reload keyboard** is available for a manual refresh.
3. Choose one of four layers, click a physical key, search the catalogue, and
   click **Assign selected keycode** (or double-click the catalogue entry).
4. Review the staged changes across all layers. **Discard edits** is local only.
5. Choose **Review and apply…**, inspect Details, and explicitly confirm.
   Keep the keyboard connected until verification finishes.

Basic typing, navigation, modifiers, function keys, numpad keys, disabled,
transparent, mute/volume, backlight toggle, LCD toggle and the observed
`MO(0)`–`MO(3)` range are offered. The Fn label on
layer 1 reflects the observed base-layer momentary assignment, not a guarantee
that every firmware revision uses it.

Other unidentified vendor, media and lighting keycodes are shown in hex and
preserved byte-for-byte. They are not offered as new assignments. Reset,
bootloader, arbitrary raw keycodes, macros, encoder rotation and lighting settings
are deliberately excluded from the picker/MVP. The keyboard diagram fixes the
manufacturer definition's duplicate Esc matrix coordinate: Esc is `(0,0)`,
while numpad Enter is `(7,13)`.

### Identifying Fn-layer assignments

The editor names the existing media, lighting, Bluetooth-slot, Windows-key lock,
LCD-profile and key-scan-delay codes using standard numeric conventions and the
vendor's custom-function list. These additional names are **display-only
interpretations**, not a claim that every action has been tested on this
firmware. Hover a key for the exact value, matrix location, and interpretation
notes. Naming a value never rewrites or normalizes it.

In particular, `0x5221` is shown as `MO(1)*` with a note about the newer keycode
range; legacy `0x5101` is retained separately. The picker does not add these
untested interpretations as new assignable functions.

`0xFFFF` is the only still-unresolved value in the captured default map. It is
present on six visible keys of layer 1, twelve of layer 2, and four of layer 3.
Its behavior has not been established: **do not assume disabled, transparent or
reset**. The layer summary counts unresolved keys and the original bytes are
preserved. Resolving this further would require firmware documentation or
careful behavioral investigation; do not test unknown keys by holding them.

### Mouse bindings

Mouse clicks, movement and wheel scrolling can be keyboard assignments when the
firmware supports mouse keys. The GMK104's USB descriptor advertises a Mouse
application collection, but this proves report capability, **not** which
remapping codes work. This firmware mixes old/new keycode ranges and no mouse
assignments have been tested. The editor therefore does not offer speculative
mouse codes yet. Adding them requires identifying and validating the compatible
range without firmware flashing; a Linux-side remapper is another possible
route, separate from onboard bindings.

### Display buttons and knob

The top-right controls are shown in physical order: two switches, the LCD screen,
then the knob. Their captured assignments are:

| Control | Matrix | Keycode | Function |
| --- | --- | --- | --- |
| Upper switch | `5,4` | `0x7820` | Backlight on/off (short label **Light**) |
| Lower switch | `5,6` | `0x7F09` | LCD on/off (short label **LCD**) |
| Knob press | `5,7` | `0x00A8` | Mute |

The manufacturer's [GMK104 manual](https://ae01.alicdn.com/kf/Sb7ec4ad457094108ae9a7398917fc248E.pdf)
identifies those functions and describes knob rotation as counter-clockwise
volume down and clockwise volume up. The vendor layout identifies the press at
`5,7`; live reads on 2026-11-17 found the listed assignments on all four layers.
These control names are factual labels, not a copied application keycode table.

Click the round knob to stage a new **press** mapping through the same matrix
buffer path as other keys. Its label follows the current/edited keycode, not a
hardcoded Mute caption. The switches' labels likewise follow remaps; their
physical identity and exact hex value remain in tooltips and change review.

Rotation is separate from the matrix press. A read-only diagnostic using VIA
`GET_ENCODER` (`14`, hex) returned `0x0000` for both directions of encoder 0 on all
four layers. This does **not** prove the knob is unremappable, nor justify
displaying Disabled as its actual function: the manual specifies working volume
control. The diagram shows that native behavior, with rotation remapping
explicitly unverified/disabled. No `SET_ENCODER` (`15`, hex) is implemented or
sent. Changed press assignments still need hardware validation, just like other
changed mappings.

## Backups and restoration

Every successful read saves a complete, private keymap JSON backup. Apply reads
the keyboard again and refuses if it differs from the last snapshot. It then
saves another full backup **before any keymap writes**, sends only changed
two-byte words, and reads all four layers back for verification.

The backup folder is shared with screen-settings backups:

```
${XDG_DATA_HOME:-~/.local/share}/GMK104/GMK104 Studio/backups/
```

Keymap files are named `keymap-*.json` and contain a schema/device/matrix marker,
protocol version, all 960 bytes and a SHA-256 integrity checksum. The checksum
detects accidental corruption; it is not an authenticity signature.

**Load backup…** accepts GMK104 Studio keymap backups only and stages their
contents locally. It does not write the keyboard. Review and Apply to restore;
the current keymap is backed up before restoration too. Backups cover **keymaps
only**, not firmware, macros, lighting or the screen. They are not a guaranteed
recovery mechanism.

If a write fails, stop. There is no automatic retry or rollback, and the keyboard
may contain a partially applied map. The error identifies the pre-write backup.
Read again to inspect the actual state before choosing whether to restore.
Retain a usable Fn/layer key; the editor does not prove layer reachability.

### Restore defaults: bundled captured keymap

**Restore defaults** stages our own
[`gmk104-default-keymap.json`](../gmk104_app/assets/gmk104-default-keymap.json)
for review. It contains all four layers (960 bytes), including unknown/vendor
keycodes, captured from the configured wired GMK104 on 2026-11-17. Two live reads
matched before capture; no keymap writes were sent. The JSON contains no local
device paths or machine identity.

This file ships with source installs and packaged builds, so the restore target
does not depend on whatever the keyboard contains on the next launch or whether
local application data still exists. The file is our snapshot format, **not**
a VIA keyboard-layout definition. It passes the same schema, matrix, firmware
version and SHA-256 validation as backups. The app never replaces it with live
readings.

After staging, use **Review and apply…** to restore. Apply still checks the current
keyboard, saves a fresh backup and verifies the full result. Clicking Restore
defaults by itself never writes the keyboard or sends a firmware factory-reset
command.

These are the **project's saved default mappings**, not manufacturer-certified
factory defaults. The source is the configured keyboard, not a firmware image or
the vendor layout JSON. Keymap only: firmware, macros, lighting and screen
settings are not restored.

### Extra first-read recovery baseline

The first successfully saved keymap is also kept at:

```
${XDG_DATA_HOME:-~/.local/share}/GMK104/GMK104 Studio/backups/baseline/keymap.json
```

Later reads, edits, applies and restores **never replace this baseline**. It is
published atomically only after the full file is flushed, and checked with the
same schema and checksum validation as other backups. A corrupt baseline is not
silently regenerated; saving/loading fails safely and Apply is blocked.

This extra local fallback is retained independently of the bundled defaults.
Use **Load backup…** and select this file if you need that first-read snapshot
instead of the project's bundled defaults, then review and Apply.

This is the **first observed configuration, not guaranteed factory defaults**.
If the keyboard was remapped before baseline capture, those mappings are part
of the baseline. The vendor layout JSON does not supply a verified factory
keymap. Baseline storage is local to this app installation, not keyboard serial
number; when changing keyboards, verify it belongs to the intended device.
Keep an additional copy elsewhere if you need protection against local data loss.

Automatic loading refreshes clean mappings on tab entry, and waits/reloads after
connection changes while the tab is active. It never discards staged edits or
overlaps screen uploads. Periodic connection checks do not repeatedly read a
connected keyboard; after a read error, use Reload or reopen the tab to retry.

## Protocol and tested scope

- Device `320f:5055`, interface 1, exact observed descriptor, usage
  `0xFF60/0x61`, unnumbered 32-byte HID input/output reports.
- Observed protocol version **`0x00FF`**, four layers, 8 rows × 15 columns,
  big-endian 16-bit keycodes in layer/row/column order.
- Allowlisted commands: `01` protocol, `11` layer count, `12` buffer read,
  `13` buffer write (hexadecimal). No EEPROM reset or firmware commands.
- Reads use at most 28 bytes per request. Writes use one aligned two-byte
  keymap word per request; acknowledgments must echo the offset and length.
- The stock VIA single-key read (`04`) did not return a standard reply during
  this investigation and is not used. Do not infer stock QMK keycode ranges
  from the firmware's version value.

On 2026-11-17, a full keymap backup was saved on the connected keyboard, the
existing base-layer A word at `(3,1)` (offset 92) was written back once unchanged,
and a full 960-byte read matched the backup. This verifies the unchanged-write
path on one device. The keyboard owner subsequently reported successful changed
keymap writes using the app. This is a user-reported behavioral result, not an
independent capture or exhaustive validation of all assignments.
**Persistence across power cycles and restoration remain unverified.**
Offline tests cover changes, stale snapshots, errors, backups and UI.

The app serializes screen and keymap operations within its window. Other
programs do not share that guard: do not run VIA concurrently. Disconnects,
power loss, firmware differences and simultaneous external edits remain risks.

## Licensing

The implementation and small catalogue are original MIT-licensed project code.
No VIA application source, parser or keycode table is copied. Basic keyboard
codes use USB HID usage values; the geometry is independently expressed from
hardware layout/matrix facts and observed reads. The vendor JSON is referenced
for hardware information, not bundled or presumed to have a redistribution
license:

https://cdn.shopify.com/s/files/1/0478/6913/2956/files/GMK104_VIA_JSON_File_Wired.json?v=1737958284

MIT permits closed-source derivatives while requiring preservation of its
notice. GPL-3.0 instead requires GPL-covered derivative source to be offered
when distributing those derivatives. Neither license is required merely to
implement an interoperable protocol. Qt/PySide's separate license obligations
still apply; see [third-party notices](../THIRD_PARTY_NOTICES.md).
