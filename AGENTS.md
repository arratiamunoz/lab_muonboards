# Lab muon boards

Work on `main` only. Do not create branches or pull requests for this repository.

- Read the [JANUS operations guide](janus/README.md) before interpreting logs, editing a controller, or supporting bench operations.
- Keep ordinary development offline. Use mocked transports and synthetic run data. Do not launch JANUS, connect to a detector, start an acquisition, or change bench settings from repository tests or CI.
- Live work belongs to the authorized bench workflow. Keep the approved bias setpoint, current limit, interlocks, and physical protections intact. Verify identity, acquisition status, and device bias state independently. A software voltage number does not override trusted board state or an approved physical measurement.
- Report terminal states accurately: START not accepted, acquiring, partial, saved, or hardware state unresolved. Report bias ON/OFF separately from acquisition and file state. Never infer saved events from raw trigger counters or a green dashboard indicator.
- Preserve partial data. After a connection drop use a bounded reconnect under the approved recovery procedure. Start a new run number only when verified board, acquisition, bias, and interlock conditions permit it. If stop or bias OFF cannot be verified, do not start again. Escalate to the bench cutoff procedure.
- Keep host-specific paths, addresses, serials, credentials, live profiles, run output, and vendor binaries/source out of new commits. Synthetic test profiles must not be directly deployable.
- Keep plots publication quality and use the established HEP style. Compare channel-matched, duration-normalized data across gain settings and clearly distinguish saved trigger counts, missing IDs, and incomplete files.
