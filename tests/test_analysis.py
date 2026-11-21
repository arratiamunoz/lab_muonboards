import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np

ANALYSIS = Path(__file__).resolve().parents[1] / "analysis"
sys.path.insert(0, str(ANALYSIS))
from adc_mip import read_histograms
from fit import EDGES, GRID_START, STEP, dist, fit_accepted, fit_spectrum, mode
from plot import garwood


class AnalysisTests(unittest.TestCase):
    def test_csv_does_not_mix_boards(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.csv"
            path.write_text("// fixture\nTrg_Id,Board_Id,CH_Id,PHA_HG,PHA_LG\n"
                            "1,0,0,63,64\n1,0,1,8191,-1\n"
                            "2,0,17,512,256\n3,1,0,4096,4096\n")
            hist, triggers, rejected = read_histograms(path)
            self.assertEqual((hist.sum(), triggers, rejected), (3, 2, 1))
            self.assertEqual(hist[0, 0, 0], 1)
            self.assertEqual(hist[1, 0, 1], 1)
            self.assertEqual(hist[0, 1, 127], 1)

    def test_garwood_limits(self):
        lo, hi = garwood([0, 1, 10])
        np.testing.assert_allclose(lo, [0, 0.172753779, 6.891305561], rtol=1e-7)
        np.testing.assert_allclose(hi, [1.841021645, 3.299526559, 14.266949761], rtol=1e-7)

    def test_peak_recovery_and_cli_smoke(self):
        model = (1750.0, 155.0, 240.0)
        indices = ((EDGES - GRID_START) / STEP).astype(int)
        cdf = np.r_[0, np.cumsum(dist(*model))]
        probabilities = np.diff(cdf[indices])
        probabilities /= probabilities.sum()
        expected = np.rint(24000 * probabilities + 2).astype(int)
        fit = fit_spectrum("LG", expected)
        self.assertIsNotNone(fit)
        self.assertTrue(fit_accepted(fit), fit["flags"])
        self.assertAlmostEqual(fit["mpv"], mode(*model), delta=30.0)
        self.assertGreater(fit["err"], 0)
        self.assertEqual(len(fit["alts"]), 2)
        self.assertIsNone(fit_spectrum("HG", np.zeros(128)))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / "synthetic.csv"
            out = root / "output"
            codes = np.repeat((EDGES[:-1] + 32), expected // 4)
            with data.open("w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(["Trg_Id", "Board_Id", "CH_Id", "PHA_HG", "PHA_LG"])
                writer.writerows((i, 0, 0, min(8191, 2 * int(code)), code)
                                 for i, code in enumerate(codes))
            result = subprocess.run([sys.executable, str(ANALYSIS / "adc_mip.py"),
                                     str(data), "--out-dir", str(out), "--label", "Synthetic"],
                                    text=True, capture_output=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for name in ("adc_spectra", "mip_fitted_spectra", "mip_mpv_by_channel"):
                self.assertTrue((out / f"{name}.png").read_bytes().startswith(b"\x89PNG"))
                self.assertTrue((out / f"{name}.pdf").read_bytes().startswith(b"%PDF-"))
            with (out / "mip_fit_results.csv").open(newline="") as output:
                result_csv = list(csv.DictReader(output))
            self.assertEqual(len(result_csv), 32)
            self.assertEqual(result_csv[0]["Gain"], "LG")
            self.assertLess(abs(float(result_csv[0]["Convolved_MPV_ADC"]) - mode(*model)), 60)
            self.assertEqual(result_csv[1]["Accepted"], "False")


if __name__ == "__main__":
    unittest.main()
