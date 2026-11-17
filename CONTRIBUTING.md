# Contributing

Issues and pull requests are welcome. Read [SAFETY.md](SAFETY.md) first.
The application is Linux-specific: GMK104 wired screen uploads (Custom1,
one/two frames, 500–1000 ms) and four-layer VIA keymapping on the observed
interfaces/firmware. See [keymapping scope](docs/KEYMAPPING.md).

## Setup and tests

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[build]"
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
.venv/bin/gmk104-studio
```

Prefer test-driven changes: add a failing test, implement the smallest safe
change, then run the full suite. Tests must never send USB commands.
Use mocks for transport and GUI uploads.

## Layout

| Path | Purpose |
| --- | --- |
| `gmk104_app/` | Screen/keymap UI, image preparation, local history, original icon |
| `protocol/gmk104.py` | Packet encoding, readback, backup, Linux HID transport, CLI |
| `protocol/via.py` | Strict VIA buffer transport, full keymap backup/apply/verification |
| `tests/` | Offline tests, generated test artwork, sanitized regression evidence |
| `docs/` | Protocol, build, and release documentation |
| `packaging/` | AppImage launcher, desktop entry, AppStream metadata |
| `scripts/` | Build, fixture-generation and offline screenshot tools |
| `.github/workflows/` | Test, bundle, and tagged-release automation |

## Protocol work

Do not broaden device matching or guess opcodes. Attach evidence and distinguish
observations from hypotheses. Readback must succeed and backups must be saved
before any upload/configuration write. Preserve unknown fields and do not retry
state-changing operations after timeouts.

Raw USB captures can contain keyboard input and unintended application memory.
Do not commit captures, personal artwork, vendor software, credentials, or local
settings. The fixture summarizer includes only selected protocol evidence and
image hashes. Inspect generated output before sharing it.

To regenerate the included original test artwork:

```bash
.venv/bin/python tests/make_artwork.py
```

Hardware tests are opt-in and separate from CI. Describe your firmware, device,
desktop, and distribution when reporting results. Never treat passing mocked
tests as proof of hardware safety.

## Releases

See [docs/BUILDING.md](docs/BUILDING.md). Keep `pyproject.toml`,
`gmk104_app/__init__.py`, AppStream metadata, changelog, and release notes in sync.
Contributions to this project are provided under its MIT license.
