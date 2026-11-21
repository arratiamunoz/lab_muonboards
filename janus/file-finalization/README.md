# JANUS 5.0.4: safer run file finalization

**Source patch and offline tests. Not installed or tested with live hardware.**

For the [CAEN JANUS 5.0.4 Windows package](https://caen.it/products/janus/) dated 6 Nov 2026, with bundled FERSlib 2.2.5. The package identifies its build as `release/v5.0.4`, revision `d9185db14aeeb4c7bd98049d989d59354e7332bc`. The exact revision was not available in CAEN’s public GitHub repository when checked; the public [JANUS](https://github.com/caenspa/janus-5202/blob/main/ReleaseNotes.txt) and [FERSlib](https://github.com/caenspa/caen-ferslib/blob/main/ReleaseNotes.txt) branches reported 5.0.1 and 2.2.2, respectively. Use the vendor package, not either public `main` branch, and verify the source SHA-256 below. The runner also accepts the exact LF-normalized text copies.

- `src/JanusC.c`: `fa309409c8f45bb966728881911f24a97acebc1f37f0aa24ed6906941539f1bf`
- `src/outputfiles.c`: `dbe6e92985b7be462dd054fdab939b10f361417d2c5d70d9c769c6d8e80f4879`

## What changes

- Requested data streams are opened without overwriting existing runs. File-open failures block acquisition; a rejected FERS start closes preopened streams and retains partial files. Use an unused run number after an interrupted or failed start; no implicit overwrite or append to an old run. The same applies to generic negative-run output names. Repeated interactive histogram/threshold snapshots under a previously used run number report an existing-file error rather than replacing the prior snapshot; use a new output/run number to save independently.
- Write, flush, sync, and close failures record the affected path and OS error. Independent streams are still closed. Existing data filenames never move; live shared read-only preview is compatible.
- JANUS checks the native STOP result and output closes before publishing RunInfo. RunInfo is written to a same-directory `.partial` sibling and published without replacing an old final file. A metadata failure preserves existing data and any partial file, and prevents the native “Output file(s) saved” success message. This also removes the duplicate last configuration line from stock RunInfo.
- Events keep the stock format, buffering and flush cadence. Files still open at terminal stop get one checked content sync, in addition to checked flush and close. Closed rollover segments get checked flush/close without a synchronous barrier in the acquisition loop. A checked final file sync and flush/close are distinct; this is not a guarantee against power loss, unsupported filesystem semantics, or events never received by the process. FERSlib-owned raw file internals, board STOP semantics, trigger settings, bias, and protections are unchanged. The tested configuration has FERS raw output disabled.

## Verify & apply to a copy only

1. Run the isolated exact-source test (Linux/glibc, Python 3, git, GCC): `python3 verify_offline.py /path/to/stock/Janus_5202_5.0.4_20261106_windows`. It compiles the two real vendor translation units with a fake FERS device and tests 6,184 simulated dual-gain, 64-channel events; no full app, device network or hardware is used.
2. On Windows, `python test_windows_file_api.py` exercises actual Windows file APIs with a preview reader open, without JANUS or a device. This is not a Windows executable build.
3. In a **new full copy** of the exact vendor source/build tree, verify original hashes (PowerShell `Get-FileHash`), normalize **just the two named staged source files** from CRLF to LF (the patch is LF), and run `git apply --check /path/to/janus-file-finalization.patch`, then `git apply /path/to/janus-file-finalization.patch`. Keep the untouched stock folder and executable separately. No configs needed for source tests.
4. For a new Windows executable use the existing CAEN project and Visual Studio v143/Windows SDK, `build/Janus-5202.vcxproj`, Release/x64, and the same vendor FERSlib. Build in the copy, not into the stock installation. A candidate Windows executable has not been produced or tested.
5. Before considering a live replacement, qualify the exact Windows executable in a disconnected test and then a separately authorized attended comparison. Require the native STOP, successful file finalization, importable exact outputs, and retained partials on forced I/O trouble. A genuine native RunInfo means an orderly file save, not that the configured preset duration completed; check the acquisition duration and trigger rows separately. If rollback is necessary, discard/revert the staged patch and use the never-modified stock package (don't delete data or partials).

## Evidence and limits

Three stock long runs reached device STOP, then terminated on the same CRT invalid-argument fail-fast address before the native RunInfo/saved receipt. The patch hardens the principal suspect and adjacent file paths. The stock caller could not be conclusively identified without a symbolized crash stack. The package contains no vendor binary/source tree, acquisition data, live settings, or device credentials.


The patch applies to CAEN’s GPL-covered JANUS source; retain the vendor notices and license when distributing patched source. See CAEN’s [COPYING](https://github.com/caenspa/janus-5202/blob/main/COPYING).
