# TASK: Package kautoswitch as .deb + install as service (for another machine)

You must turn the existing repo into a proper Debian package (.deb) that:
- installs on a clean Ubuntu KDE machine (NOT the dev machine)
- runs as a user service (systemd --user) to hook X11 input in the user session
- provides a tray GUI autostart in KDE
- provides a post-install smoke test + easy manual verification steps
- does NOT rely on /opt/ai/ninja/... paths
- does NOT require internet at runtime
- uses system python packages (no venv requirement for runtime)

## Constraints / realities (do not ignore)
- XRecord/XTest require an X11 session; the hook must run under the logged-in user with DISPLAY set.
- Therefore: package must install a **systemd user unit**, not a system-wide root daemon.
- GUI tray also must run under the user session.

## Deliverables (must commit into repo)
1) `debian/` packaging directory:
   - debian/control
   - debian/changelog
   - debian/rules
   - debian/compat (if needed) or use debhelper-compat
   - debian/copyright
   - debian/source/format
   - debian/kautoswitch.install (or equivalent)
   - debian/kautoswitch.postinst
   - debian/kautoswitch.prerm
   - debian/kautoswitch.lintian-overrides (only if truly needed)
2) systemd user unit:
   - `packaging/systemd/kautoswitch.service` (installed to `/usr/lib/systemd/user/kautoswitch.service`)
3) desktop entry for KDE autostart:
   - `packaging/autostart/kautoswitch-tray.desktop` (installed to `/etc/xdg/autostart/kautoswitch-tray.desktop`)
4) scripts:
   - `scripts/build_deb.sh` (build inside a clean env possible)
   - `scripts/smoke_test_local.sh` (run after install)
5) README update:
   - “Install from .deb”
   - “Enable/disable service”
   - “Troubleshooting on target machine”
6) Must keep existing tests; add a “packaging smoke test” if needed.

## Packaging approach (required)
- Use `debhelper` + `dh_python3` + `pybuild`.
- Do NOT ship a virtualenv.
- Add Python dependencies as Debian deps where possible.
- If some deps are not available as Ubuntu packages, you must:
  - either vendor them (only if license ok),
  - or reduce dependency usage,
  - but do NOT require pip-install on target machine for runtime.

## Required runtime layout
- Install python package to standard location (via dh_python3).
- Install config dir default:
  - `/etc/kautoswitch/config.json` (optional) OR none; per-user config in `~/.config/kautoswitch/config.json`
- Ensure `kautoswitch/resources/tinyllm_prompt.md` is included in installed package.

## systemd user service requirements
- Unit name: `kautoswitch.service`
- Must run:
  - `ExecStart=/usr/bin/python3 -m kautoswitch.main --daemon`
  - OR provide a small wrapper installed to `/usr/bin/kautoswitch-daemon`
- Must restart on failure but avoid restart storms:
  - `Restart=on-failure`
  - `RestartSec=1s`
- Must set a sane environment for X11:
  - Prefer not hardcoding DISPLAY.
  - Use service started after graphical session:
    - `After=graphical-session.target`
    - `PartOf=graphical-session.target`
  - Document that on KDE, user service inherits DISPLAY when started by systemd --user within the session.
- Must NOT run as root.

## GUI tray autostart requirements
- Provide a tray entry that starts:
  - `/usr/bin/python3 -m kautoswitch.main --tray`
  - OR wrapper `/usr/bin/kautoswitch-tray`
- Must be toggleable by the user (tray has enable/disable anyway).
- Autostart via `/etc/xdg/autostart` desktop file is acceptable.

## Postinst/prerm behavior (required)
- postinst must:
  - NOT auto-enable user services globally (cannot, because it’s per-user)
  - print clear instructions:
    - `systemctl --user daemon-reload`
    - `systemctl --user enable --now kautoswitch.service`
  - optionally offer a non-failing smoke test suggestion.
- prerm must:
  - NOT break if service not enabled
  - stop user service if running for that user (best-effort)
- Never block install on missing DISPLAY.

## Build instructions (required)
Provide two supported build paths:

### Path A: build on Ubuntu host with packaging tools
- `sudo apt-get install -y devscripts debhelper dh-python python3-all`
- `dpkg-buildpackage -us -uc -b`

### Path B: build in a clean container (preferred)
- Provide `scripts/build_deb.sh` that:
  - builds via `docker` or `podman` using an Ubuntu base image
  - installs build deps
  - outputs `.deb` into `dist/`

## Dependencies (must resolve)
You must map current python requirements to Ubuntu packages.
Examples (verify actual names on Ubuntu target):
- python3-xlib
- python3-evdev (if used; but X11-only runtime is ok)
- python3-pyqt5 or python3-pyqt6
- python3-requests (if API client uses it)
- python3-pytest (for tests; build-dep only)
- spellchecker lib alternative:
  - Prefer `python3-pyspellchecker` if available as apt package.
  - If not available, replace with a small built-in spell module or vendor minimal dictionary approach.
Do not leave `pip install ...` as a runtime step.

## Acceptance: packaging + runtime verification on target machine
You must provide a checklist and commands in README:

1) Install:
- `sudo apt install ./kautoswitch_*.deb`

2) Enable service (user):
- `systemctl --user daemon-reload`
- `systemctl --user enable --now kautoswitch.service`
- `systemctl --user status kautoswitch.service`

3) Verify tray:
- confirm tray icon appears (autostart)
- right-click menu shows enable/disable/model/lang toggles

4) Functional manual test:
- open any text field
- type `b jy dsrk.xb` + space
- expect correction
- press undo hotkey to restore

5) Smoke test script:
- `scripts/smoke_test_local.sh`
  - must verify:
    - python module import
    - config path writable
    - unit file installed
    - desktop file installed
    - basic corrector pipeline tests (non-X11)
  - For X11 integration tests, provide “manual step” (cannot reliably in headless CI).

## Output required from you (Claude)
When done, output:
- list of new/changed files
- exact commands to build .deb
- exact commands to install and enable on a fresh machine
- any remaining limitations
- confirm no runtime pip/venv is required

Start now.
