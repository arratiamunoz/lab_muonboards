"""First-party JANUS 5.0.4 GUI-control primitives from the bench runner.

No executable entry point, device addressing or board-register write path.
Callers own the approved session and operator-controlled hardware lifecycle.
"""
import collections
import csv
import math
import re
import socket
import struct
import time

UI = {"ready": 3, "running": 4}
TELEMETRY_MAX_AGE = 3.0
STABLE_MIN_SAMPLES = 5
STABLE_SAMPLE_SPACING = .75
RAMP_UP_STABLE_S = 6.0
RAMP_DOWN_STABLE_S = 5.0

class Frames:
    def __init__(self): self.buf=bytearray()
    def feed(self, raw):
        self.buf+=raw; result=[]
        while len(self.buf)>=2:
            n=struct.unpack_from("<H",self.buf)[0]
            if not 3<=n<=16396: raise RuntimeError(f"Bad Janus frame length {n}")
            if len(self.buf)<n: break
            result.append(bytes(self.buf[2:n]).decode("utf-8","replace"))
            del self.buf[:n]
        return result

class Link:
    def __init__(self,s):
        self.s=s; self.frames=Frames(); self.queue=collections.deque()
        self.pid=None; self.ready=False; self.running=False; self.latest=None; self.err=None; self.stopped=None
        s.settimeout(.25)
    def send(self,message):
        if message not in {"h0","H1 0","H0 0","s","S","q0"}:
            raise RuntimeError("Refusing unrecognized command")
        self.s.sendall((message+"\n" if message in {"h0","H1 0","H0 0","q0"} else message).encode("ascii"))
    def current(self):
        if self.latest is None or time.monotonic()-self.latest[0]>TELEMETRY_MAX_AGE:
            raise RuntimeError("Fresh HV telemetry missing")
        return self.latest[1:]
    def feed(self,msg):
        if msg.startswith("i"):
            fields=msg[1:].split(";")
            if len(fields)>=5 and fields[0]=="0":
                if "5202" not in fields[2]: raise RuntimeError("Expected A5202 model")
                self.pid=int(fields[1])
        elif msg.startswith("a") and len(msg)>=3:
            try: state=int(msg[1:3])
            except ValueError: return
            msgtext=msg[3:].strip()
            self.ready=state==UI["ready"]; self.running=state==UI["running"]
            if state==-1 or re.search(r"Over Voltage|Over Current|ERROR",msgtext,re.I):
                self.err=msgtext or "Janus entered error state"
        elif msg.startswith("h"):
            fields=msg[1:].split()
            if len(fields)>=4 and fields[0]=="0":
                flags=int(fields[1]); v=float(fields[2]); ma=float(fields[3])
                if flags not in range(8) or not all(map(math.isfinite,(v,ma))):
                    raise RuntimeError("Bad HV telemetry")
                self.latest=(time.monotonic(),flags,v,ma)
        elif msg[:1] in ("m","e","w"):
            found=re.search(r"Run #(\d+) stopped.*Elapsed Time = ([\d.]+) s",msg)
            if found: self.stopped=(int(found.group(1)),float(found.group(2)))
    def pump(self):
        try: raw=self.s.recv(32768)
        except socket.timeout: return
        if not raw: raise RuntimeError("Janus control disconnected")
        for msg in self.frames.feed(raw): self.feed(msg)
    def wait(self,pred,seconds,ignore_fault=False,query=False):
        end=time.monotonic()+seconds; probe=0.0
        while time.monotonic()<end:
            self.pump()
            if self.err and not ignore_fault: raise RuntimeError(self.err)
            if pred(): return
            if query and time.monotonic()-probe>.65:
                self.send("h0"); probe=time.monotonic()
        raise RuntimeError("Timed out waiting for Janus condition")

class StableVoltage:
    """A continuous window from post-command, fresh telemetry; one cached reading cannot qualify."""
    def __init__(self, started, seconds, spread):
        self.started = started
        self.seconds = seconds
        self.spread = spread
        self.samples = []
    def step(self, latest, qualifies, now=None):
        now = time.monotonic() if now is None else now
        if latest is None or latest[0] < self.started or now-latest[0] > TELEMETRY_MAX_AGE:
            self.samples.clear()
            if now-self.started > TELEMETRY_MAX_AGE:
                raise RuntimeError("Stale or missing HV telemetry")
            return False
        t, _, voltage, _ = latest
        if not qualifies:
            self.samples.clear()
            return False
        # Reset before thinning so an intervening excursion cannot disappear between samples.
        if self.samples:
            voltages = [v for _,v in self.samples]
            if max(*voltages,voltage)-min(*voltages,voltage) > self.spread:
                self.samples = [(t,voltage)]
                return False
            if t-self.samples[-1][0]<STABLE_SAMPLE_SPACING:
                return False
        self.samples.append((t,voltage))
        return len(self.samples)>=STABLE_MIN_SAMPLES and t-self.samples[0][0]>=self.seconds

def request_shutdown(link, confirmed_off, timeout_s):
    """Use the established GUI STOP/OFF sequence and require fresh OFF evidence.

    A caller-supplied, bench-approved predicate checks the local OFF profile.
    This request does not supply a command or independent hardware ACK.
    """
    failures = []
    try:
        link.send("S")
    except (OSError, RuntimeError) as exc:
        failures.append(str(exc))
    started = time.monotonic()
    stable = StableVoltage(started, RAMP_DOWN_STABLE_S, .10)
    try:
        link.send("H0 0")
        def ready_off():
            if link.latest is not None and link.latest[0] >= started and link.latest[1] & 2:
                raise RuntimeError("Bias monitor reported a fault during OFF verification")
            return stable.step(link.latest, confirmed_off(link) and not link.running)
        link.wait(ready_off, timeout_s, ignore_fault=True, query=True)
    except (OSError, RuntimeError) as exc:
        failures.append(str(exc))
    if failures:
        raise RuntimeError("STOP/OFF unverified; follow bench cutoff procedure: " + "; ".join(failures))
    return True


def await_bias_stability(link, settled, timeout_s):
    """Apply the runner's bounded stability logic to one authorized session.

    The supplied predicate must implement the verified bench protection policy.
    An exception or timeout is not permission to START or re-arm.
    """
    started = time.monotonic()
    stable = StableVoltage(started, RAMP_UP_STABLE_S, .08)
    link.send("H1 0")
    def stable_on():
        fresh = (link.latest is not None and link.latest[0] >= started
                 and time.monotonic() - link.latest[0] <= TELEMETRY_MAX_AGE)
        return stable.step(link.latest, settled(link) if fresh else False)
    link.wait(stable_on, timeout_s, query=True)


def settled(link, low_v, high_v, current_limit_ma):
    """Legacy supervised GUI policy for a bench with a validated monitor."""
    flags, voltage, current = link.current()
    if flags & 2 or not 0 <= current < current_limit_ma or not 0 <= voltage <= high_v:
        raise RuntimeError(f"Bias protection gate: flags={flags} Vmon={voltage} Imon={current}")
    return flags == 1 and low_v <= voltage <= high_v


def validate_csv(p):
    times={}; masks={}
    with p.open(encoding="utf-8-sig",newline="") as f:
        for line in f:
            if not line.startswith("//"): break
        for r in csv.DictReader(f,fieldnames=line.strip().split(",")):
            t,c=int(r["Trg_Id"]),int(r["CH_Id"])
            if r["Board_Id"]!="0" or not 0<=c<64 or masks.get(t,0)&(1<<c) or r["DataType"]!="0x3":
                raise RuntimeError("Unexpected CSV channel row")
            masks[t]=masks.get(t,0)|(1<<c)
            if times.setdefault(t,r["TStamp_us"])!=r["TStamp_us"]:
                raise RuntimeError("Timestamp disagrees within trigger")
    if not masks or not all(x==(1<<64)-1 for x in masks.values()):
        raise RuntimeError("CSV empty or missing channels from saved events")
    return len(masks)

DURATIONS = {"PTRG": 60, "TLOGIC": 1800}


def config_values(text):
    """Parse the active, unscoped JANUS directives used in a sealed profile."""
    items = {}
    for line in text.splitlines():
        fields = line.split("#", 1)[0].strip().split(maxsplit=1)
        if len(fields) == 2:
            if fields[0] in items:
                raise RuntimeError(f"Duplicate setting: {fields[0]}")
            items[fields[0]] = fields[1].strip()
    return items


def stage_profile(baseline, hg, lg, mode, locked, allowed_gain_pairs):
    """Pin existing authorized settings and change only the named run role.

    Supply the local read-only config and its independently sealed lock values.
    The synthetic example in this repository is deliberately incomplete.
    """
    if (hg,lg) not in allowed_gain_pairs or mode not in DURATIONS:
        raise ValueError("Unsanctioned gain choice or mode")
    if not (1 <= hg <= 61 and 1 <= lg <= 61):
        raise ValueError("Unsafe raw gain endpoint")
    old = config_values(baseline)
    required = {"AcquisitionMode", "StartRunMode", "StopRunMode", "HV_Vbias",
                "HV_Imax", "EnableTempFeedback", "HV_Adjust_Range", "HV_IndivAdj",
                "TriggerLogic", "MajorityLevel", "TD_CoarseThreshold",
                "QD_CoarseThreshold", "HG_ShapingTime", "LG_ShapingTime",
                "TestPulseSource", "FastShaperInput", "GainSelect", "OF_ListCSV",
                "OF_RunInfo", "OF_ServiceInfo", "OF_RawData",
                "AskHVShutDownOnExit", "RunNumber_AutoIncr", "EnableJobs"}
    if not required.issubset(locked):
        raise RuntimeError("Incomplete protection and acquisition lock set")
    if any(old.get(k) != v for k, v in locked.items()):
        raise RuntimeError("The configuration differs from the sealed baseline")
    for key in ("HG_Gain", "LG_Gain", "BunchTrgSource", "TriggerSource", "TriggerMask",
                "PtrgPeriod", "TestPulseSource", "PresetTime"):
        matches = [p for p in old if re.match(r"(?i)^"+re.escape(key)+r"(?=$|[^a-zA-Z0-9_])", p)]
        expected = [] if key in ("TriggerSource", "TriggerMask") else [key]
        if matches != expected:
            raise RuntimeError(f"Noncanonical or scoped {key} directive")
    if old["BunchTrgSource"] != "TLOGIC":
        raise RuntimeError("Start from the sealed TLOGIC baseline")
    patch = {"HG_Gain": str(hg), "LG_Gain": str(lg),
             "PresetTime": "30 m" if mode == "TLOGIC" else "1 m"}
    if mode == "PTRG":
        patch.update(BunchTrgSource="PTRG", PtrgPeriod="55 ms")
    new = baseline
    for key, value in patch.items():
        new, n = re.subn(r"(^[ \t]*"+key+r"[ \t]+)[^#\r\n]+",
                         lambda m: m[1]+value+"  ", new, flags=re.M)
        if n != 1:
            raise RuntimeError(f"Expected exactly one {key} line")
    if config_values(new) != {**old, **patch}:
        raise RuntimeError("Unscoped config change")
    return new
