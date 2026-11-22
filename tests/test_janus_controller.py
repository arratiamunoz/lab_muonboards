"""Offline tests: synthetic bytes and fake GUI transports only."""
import io
import unittest

from janus import controller as c


class FakeSocket:
    def __init__(self, response=b""):
        self.response = response
        self.sent = []

    def settimeout(self, _):
        pass

    def sendall(self, data):
        self.sent.append(data)

    def recv(self, _):
        return self.response


def frame(s):
    payload = s.encode("ascii")
    return (len(payload) + 2).to_bytes(2, "little") + payload


class FakePath:
    def __init__(self, data):
        self.data = data

    def open(self, **_kwargs):
        return io.StringIO(self.data)


def example_csv(n=64, mismatch=False):
    data = ["// Synthetic fixture",
            "Trg_Id,CH_Id,Board_Id,DataType,TStamp_us,PHA_HG,PHA_LG"]
    for i in range(n):
        data.append(f"5,{i},0,0x3,{11 if mismatch and i else 10},200,100")
    return "\n".join(data) + "\n"


def fixture():
    locked = c.config_values("""
AcquisitionMode SPECTROSCOPY
StartRunMode ASYNC
StopRunMode PRESET_TIME
HV_Vbias LOCAL_APPROVED_SETPOINT
HV_Imax LOCAL_APPROVED_CURRENT
EnableTempFeedback LOCAL_APPROVED_TEMP_POLICY
HV_Adjust_Range LOCAL_APPROVED_TRIM_RANGE
HV_IndivAdj LOCAL_APPROVED_TRIM
TriggerLogic MAJ64
MajorityLevel 2
TD_CoarseThreshold LOCAL_APPROVED_TD
QD_CoarseThreshold LOCAL_APPROVED_QD
HG_ShapingTime LOCAL_APPROVED_HG_SHAPING
LG_ShapingTime LOCAL_APPROVED_LG_SHAPING
TestPulseSource OFF
FastShaperInput HG-PA
GainSelect BOTH
OF_ListCSV 1
OF_RunInfo 1
OF_ServiceInfo 1
OF_RawData 0
AskHVShutDownOnExit 1
RunNumber_AutoIncr 0
EnableJobs 0
""")
    local = dict(locked, HG_Gain="2", LG_Gain="3", BunchTrgSource="TLOGIC",
                 PtrgPeriod="1 ms", PresetTime="30 m")
    return "\n".join(f"{key} {value}" for key, value in local.items()) + "\n", locked


class ControllerTests(unittest.TestCase):
    def test_frames_accept_fragmentation_and_coalescing(self):
        f = c.Frames()
        a = frame("h 0 0 0 0")
        self.assertEqual(f.feed(a[:3]), [])
        self.assertEqual(f.feed(a[3:] + frame("a03READY")), ["h 0 0 0 0", "a03READY"])

    def test_frames_reject_bad_length(self):
        with self.assertRaisesRegex(RuntimeError, "frame length"):
            c.Frames().feed(b"\x02\x00")

    def test_gui_command_allowlist(self):
        sock = FakeSocket()
        link = c.Link(sock)
        link.send("H0 0")
        link.send("s")
        with self.assertRaisesRegex(RuntimeError, "Refusing"):
            link.send("H1 4")
        self.assertEqual(sock.sent, [b"H0 0\n", b"s"])

    def test_ctrl_disconnect_is_not_ready(self):
        with self.assertRaisesRegex(RuntimeError, "disconnected"):
            c.Link(FakeSocket()).pump()

    def test_status_and_native_stop_are_independent(self):
        link = c.Link(FakeSocket(frame("a04RUNNING") +
                                 frame("mRun #123 stopped. Elapsed Time = 60.00 s")))
        link.pump()
        self.assertTrue(link.running)
        self.assertEqual(link.stopped, (123, 60))

    def test_invalid_telemetry_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "Bad HV telemetry"):
            c.Link(FakeSocket()).feed("h 0 1 nan 0")

    def test_legacy_gate_rejects_alarm_or_limit(self):
        class Telemetry:
            def __init__(self, reading):
                self.reading = reading
            def current(self):
                return self.reading
        for bad in [(3, 7.0, .01), (1, 7.3, .01), (1, 7.0, .50)]:
            with self.assertRaisesRegex(RuntimeError, "protection gate"):
                c.settled(Telemetry(bad), 6.8, 7.2, .5)

    def test_stale_and_overspread_samples_cannot_qualify(self):
        v = c.StableVoltage(10.0, 5.0, .10)
        self.assertFalse(v.step((10.0, 0, 1.0, 0.0), True, now=10.0))
        self.assertFalse(v.step((10.2, 0, 1.2, 0.0), True, now=10.2))
        self.assertEqual(v.samples, [(10.2, 1.2)])
        with self.assertRaisesRegex(RuntimeError, "Stale"):
            v.step((10.2, 0, 1.2, 0.0), True, now=14.0)

    def test_shutdown_attempt_is_not_confirmation(self):
        class BrokenLink:
            def __init__(self):
                self.commands = []
            def send(self, msg):
                self.commands.append(msg)
            def wait(self, *_args, **_kwargs):
                raise RuntimeError("timed out")
        x = BrokenLink()
        with self.assertRaisesRegex(RuntimeError, "OFF unverified"):
            c.request_shutdown(x, lambda _: False, 1)
        self.assertEqual(x.commands, ["S", "H0 0"])

    def test_no_csv_claim_for_partial_event(self):
        self.assertEqual(c.validate_csv(FakePath(example_csv())), 1)
        with self.assertRaisesRegex(RuntimeError, "missing channels"):
            c.validate_csv(FakePath(example_csv(63)))

    def test_timestamp_mismatch_is_not_assert_dependent(self):
        with self.assertRaisesRegex(RuntimeError, "Timestamp"):
            c.validate_csv(FakePath(example_csv(mismatch=True)))

    def test_stage_matches_only_intended_deltas(self):
        text, locked = fixture()
        before = c.config_values(text)
        p = c.config_values(c.stage_profile(text, 4, 5, "PTRG", locked, {(4, 5)}))
        self.assertEqual(p, dict(before, HG_Gain="4", LG_Gain="5",
                                 BunchTrgSource="PTRG", PtrgPeriod="55 ms", PresetTime="1 m"))
        p = c.config_values(c.stage_profile(text, 4, 5, "TLOGIC", locked, {(4, 5)}))
        self.assertEqual(p, dict(before, HG_Gain="4", LG_Gain="5"))

    def test_stage_rejects_scoped_and_changed_protection(self):
        text, locked = fixture()
        for bad in (text+"HG_Gain[0] 9\n",
                    text.replace("HV_Vbias LOCAL_APPROVED_SETPOINT", "HV_Vbias DIFFERENT")):
            with self.assertRaises(RuntimeError):
                c.stage_profile(bad, 4, 5, "PTRG", locked, {(4, 5)})
        with self.assertRaisesRegex(RuntimeError, "Incomplete"):
            c.stage_profile(text, 4, 5, "PTRG", {}, {(4, 5)})
