# Building TournamentManager.exe on Windows

> **Status: not yet tested on Windows.** The build script and packaging were checked with a macOS build (all modules bundled, pages served, log and save folder created correctly). Until someone completes the checklist below on a real Windows PC, treat the `.exe` as experimental.

The build has to run **on Windows**. PyInstaller cannot make a Windows `.exe` from a Mac.

## 1. One-time setup (about 10 minutes)

1. Install **Python 3.9 or newer** from https://www.python.org/downloads/windows/ (the Microsoft Store version is not supported).
   - On the first installer screen, tick **"Add python.exe to PATH"**.
   - Keep the default **"tcl/tk and IDLE"** option ticked (Tkinter needs it).
2. Get the project:
   - With Git: `git clone https://github.com/jbutler0831/tournament-manager.git`
   - Without Git: on GitHub click **Code → Download ZIP**, then right-click the ZIP and choose **Extract All**.

## 2. Build (about 3–5 minutes the first time)

1. Open **Command Prompt** (Start menu → type `cmd`).
2. Go to the project folder, for example:
   ```
   cd %USERPROFILE%\Downloads\tournament-manager
   ```
3. Run:
   ```
   build_windows.bat
   ```

The script does five steps and stops at the first error:

| Step | What it does |
|---|---|
| 1/5 | Checks for Python 3.9+ and Tkinter |
| 2/5 | Creates a separate build environment in `.venv-build\` (your main Python is not changed) |
| 3/5 | Installs `qrcode` and PyInstaller into that environment |
| 4/5 | Runs all unit tests. If any fail, **no .exe is built** |
| 5/5 | Builds `dist\TournamentManager.exe` (one file, no console window) |

Success ends with: `Done: dist\TournamentManager.exe`

The `.exe` is self-contained. Copy it anywhere (Desktop, USB stick). Players' phones and the TV don't need anything installed.

## 3. Where the data goes

The packaged app keeps everything in your **Documents** folder:

```
Documents\TournamentManager\
    tournament_save.pkl                  current tournament (saved after every change)
    tournament_save-YYYYMMDD-HHMMSS.pkl  older tournaments (kept when you start a new one)
    tournament_manager.log               error log (send this file with bug reports)
```

If your Documents folder is synced by OneDrive, this folder is inside the OneDrive Documents folder.

Running from source (`python tournament_manager.py`) still saves next to the script, exactly like on macOS.

## 4. First launch: expected Windows warnings

1. **"Windows protected your PC" (SmartScreen).** The `.exe` is not code-signed. Click **More info → Run anyway**.
2. **Windows Defender Firewall prompt.** Tick **both Private and Public networks**, then **Allow access**. Venue Wi-Fi is usually treated as *Public*; if you only allow Private, phones and the TV won't connect.
3. **Antivirus warning.** One-file PyInstaller programs are sometimes flagged by mistake. If it happens, report it with the antivirus name.

## 5. Windows test checklist (about 25 minutes)

Do the full [practice tournament checklist](TESTING_CHECKLIST.md) using `dist\TournamentManager.exe` instead of `python3 tournament_manager.py`, plus these Windows-specific checks:

- [ ] Build finishes with `Done: dist\TournamentManager.exe` and `Ran 16 tests … OK` in the output.
- [ ] Double-clicking the `.exe` opens the app window with **no black console window**.
- [ ] `Documents\TournamentManager\tournament_manager.log` exists and contains a `--- Tournament Manager started …` line.
- [ ] The address shown in the app (`http://<ip>:8000`) opens on a phone on the same Wi-Fi.
- [ ] **Open TV Display** opens the TV page in the default browser.
- [ ] The QR window shows a scannable code.
- [ ] After the first change, `tournament_save.pkl` appears in `Documents\TournamentManager\`.
- [ ] Close the app mid-match, reopen the `.exe`, click **Yes**: the live match and results are restored.
- [ ] Copy the `.exe` to another folder (e.g. Desktop) and run it: it resumes the **same** tournament.
- [ ] Champion screen shows `👑 TOURNAMENT CHAMPION: <name> 👑` without errors (emoji may show as a box; that is cosmetic).
- [ ] Choose **No** at "Resume tournament?": the old save is renamed with a timestamp, not deleted.
- [ ] After testing, the log contains no `Traceback` lines. If it does, attach the log to a bug report.

Record: Windows version (10/11), Python version (`py --version`), and any failures.

## Troubleshooting

| Message | Fix |
|---|---|
| `ERROR: Python was not found.` | Install Python from python.org with "Add python.exe to PATH" ticked, then open a **new** Command Prompt. |
| `Python was not found; run without arguments to install from the Microsoft Store` | Windows' Store shortcut is answering instead of real Python. Install from python.org, or turn off the `python.exe` "App execution alias" in Settings. |
| `ERROR: Tkinter is missing.` | Re-run the Python installer → **Modify** → tick **tcl/tk and IDLE**. |
| Firewall prompt for **Python** during step 4/5 | A test briefly starts the web server. Clicking **Cancel** is fine; the tests still pass. |
| `ERROR: Tests failed.` | Don't use an old `.exe`. Report the failing test name in a bug report. |
| Phones can't open the page | Allow the app on **Public** networks in Windows Defender Firewall, and check the venue Wi-Fi doesn't block device-to-device traffic. |

## Clean rebuild

Delete these, then run `build_windows.bat` again:

```
rmdir /s /q build dist .venv-build
del TournamentManager.spec
```
