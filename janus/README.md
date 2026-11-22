# JANUS control and run interpretation

[NeoLattice Autonomous Lab](https://neolattice-autonomous-lab.nandux-6751.chatgpt.site) shows ongoing runs and run status. Use it to monitor, not to infer that a command reached the board or that output is complete.

## What is here

- [`controller.py`](controller.py) contains first-party primitives adapted from the actual supervised JANUS controller: framed GUI receive, allowlisted commands, fresh telemetry windows, shutdown request handling, sealed config staging, and dual-gain event completeness validation. It requires an existing authorized control transport; it cannot discover or launch a bench by itself.
- [File finalization patch](file-finalization/README.md) covers checked writes, flush and sync, native RunInfo publication, and preservation of partial files. Obtain matched JANUS and FERSlib releases via CAEN and follow the patch guide. Do not replace a running installation.
- Hardware-specific configuration, launch credentials, direct board recovery writes, standalone live launchers and diagnostic builds are intentionally outside this public repository.

## Authorized bench run

1. **Preflight.** Use the approved onsite workflow. Verify there is one owner and the board matches the local hardware identity and firmware profile. Independently verify acquisition idle/ready, initial bias state, faults, approved setpoint and current limit, all interlocks, and an unused run number. A connected socket alone does not mean a live acquisition is ready. Read the local sealed configuration, diff the intended changes, and preserve the exact config with run output.
2. **Prepare a matched pair.** Take the periodic `PTRG` pedestal run for 60 seconds at 55 ms, then the 30-minute `TLOGIC` run with the approved majority trigger. Keep gain, shaping, thresholds, geometry and bias matched between the two roles and use distinct run numbers. The periodic measurement provides a mean and spread for each channel. Compare the signal peak from the majority-trigger run against that matched baseline.
3. **Start and observe.** Require positive native START evidence and fresh control state. Separate ready, ramping, and acquiring. Use the bench-approved supervision policy for an unreliable monitor; do not treat `settled()` as a substitute for local policy. Its GUI-only voltage window is for a validated monitor. Hardware protections and physical restraints stay in place.
4. **Stop and verify.** Confirm native STOP, then verify independent board idle and safe bias state. Require checked file closes and native RunInfo before labeling the run complete. Keep exact configuration, timestamps, and files with SHA-256 verification. Do not reuse an interrupted run number.

## Read the evidence correctly

| Signal | Meaning |
| --- | --- |
| GUI status, `Vmon`, and `Imon` | Operational telemetry. GUI ramp messages can represent a requested state in the application loop; stale or unreliable telemetry is not proof of analog output voltage. |
| Device readback | The supported firmware reports bias switch, ramp, and alarm bits separately. An ON indication or missing OFF readback blocks rearm; it is not a voltmeter. The acquisition state is independent of bias. |
| Controller send or socket acknowledgement | The first confirms queuing; a relevant native device response confirms the command transaction, not independently that the requested state was reached. Require positive readback. |
| Native STOP, stream sync/close and final RunInfo | Distinct evidence. Even a clean host save is not proof that a producer FIFO drained. Without a documented completion marker or accepted-frame count, keep that result distinct from a proved hardware boundary. |
| List CSV | Count complete, channel-consistent events, then divide by measured exposure. Track missing trigger IDs separately. An ID gap is not, by itself, proof of network or file loss. |

## Interruption and shutdown

A JANUS ramp routine can block its GUI command loop. The controller may send OFF while the application is still in that loop. A send is not an OFF acknowledgement. Preserve partial files, keep the interlocks intact, and use the existing bounded, approved recovery procedure. If control or safe bias cannot be verified, follow the local A5202 12 V cutoff procedure; do not unplug an energized SiPM or rearm. Do not reconnect an acquisition while an energized or unresolved session owns the board. Close only the stale session after the board is safe; start a new run number only after identity, idle, bias, and protections are verified.

## Offline checks

From the repository root:

```sh
python -m unittest discover -s tests -p 'test_janus_controller.py' -v
```

The controller tests use synthetic profiles, framed messages, mock transports, and fabricated events. There is no board connection. For the native file patch, follow its separate exact-source verification instructions. Treat offline test results as software verification, not a bench readiness decision.
