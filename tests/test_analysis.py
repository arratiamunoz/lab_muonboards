import csv
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ANALYSIS = Path(__file__).resolve().parents[1] / "analysis"
sys.path.insert(0, str(ANALYSIS))
from adc_mip import read_histograms, run_metadata_label
from fit import EDGES, GRID_START, STEP, dist, fit_accepted, fit_spectrum, mode
from lg_hg_slope import fit as gain_fit, fit_window, read_pairs
from plot import garwood, plot_mpv, plot_spectra
from refine import GAUSSIAN, estimate_peak
from scipy.special import ndtr


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

    def test_run_metadata(self):
        label = run_metadata_label(1200, 3600)
        self.assertEqual(label, "Duration: 1,200.00 s \u00b7 Triggers: 3,600 \u00b7 Trigger rate: 3.00 Hz")

    def test_plot_headers_show_metadata_without_confidence_text(self):
        label = run_metadata_label(1200, 3600)
        counts = np.zeros((2, 16, 128), dtype=int)
        counts[0, 0, 50] = 5
        fit = {"mpv": 1800, "stat_low": 15, "stat_high": 22, "variation_lo": 1700,
               "variation_hi": 1850, "curve_x": [1600, 1800, 2000],
               "curve_y": [1, 5, 1], "model": GAUSSIAN}
        captured = []

        def check(figure, dest):
            text = [item.get_text() for item in figure.texts]
            self.assertIn(label, text)
            self.assertFalse(any("68." in item or "confidence" in item for item in text))
            captured.append(dest.name)

        with patch("plot.save", side_effect=check):
            plot_spectra(counts, Path("."), "Synthetic", label, "", 60)
            plot_spectra(counts, Path("."), "Synthetic", label, "", 65, {"LG00": fit})
            plot_mpv({"LG00": fit}, Path("."), "Synthetic", label)
        self.assertEqual(captured, ["adc_spectra", "mip_fitted_spectra", "mip_mpv_by_channel"])

    def test_paired_gain_fit_and_window(self):
        x = np.array([0, 700, 1500, 2000, 5000, 6500, 8000])
        y = np.rint(50 + .38 * x).astype(int)
        expected = [False, True, True, True, True, True, False]
        np.testing.assert_array_equal(fit_window(x, y), expected)
        selected = fit_window(x, y)
        intercept, slope, error = gain_fit(x[selected], y[selected])
        self.assertAlmostEqual(slope, .38)
        self.assertAlmostEqual(intercept, 50)
        self.assertGreaterEqual(error, 0)
        self.assertIsNone(gain_fit(x[:2], y[:2]))
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / "paired.csv"
            data.write_text("Trg_Id,Board_Id,CH_Id,PHA_HG,PHA_LG\n"
                            "1,0,0,1000,430\n1,0,1,2000,810\n2,1,0,3000,1190\n")
            groups, count = read_pairs(data, 0)
            self.assertEqual(count, 1)
            np.testing.assert_array_equal(groups[0], [[1000, 430]])
            np.testing.assert_array_equal(groups[1], [[2000, 810]])

    def test_garwood_limits(self):
        lo, hi = garwood([0, 1, 10])
        np.testing.assert_allclose(lo, [0, 0.172753779, 6.891305561], rtol=1e-7)
        np.testing.assert_allclose(hi, [1.841021645, 3.299526559, 14.266949761], rtol=1e-7)

    def test_gaussian_limit_keeps_mode_and_profiles_intervals(self):
        peak, width = 1850.0, 420.0
        masses = np.diff(ndtr((EDGES - peak) / width))
        counts = np.rint(18000 * masses + 15).astype(int)
        fit = estimate_peak("LG", counts)
        self.assertIsNotNone(fit)
        self.assertEqual(fit["model"], GAUSSIAN)
        self.assertEqual(fit["stat_method"], "Minuit2 MINOS")
        self.assertAlmostEqual(fit["mpv"], peak, delta=10)
        self.assertGreater(fit["stat_low"], 0)
        self.assertGreater(fit["stat_high"], 0)
        self.assertLessEqual(fit["variation_lo"], fit["mpv"])
        self.assertGreaterEqual(fit["variation_hi"], fit["mpv"])
        self.assertEqual(len(fit["curve_x"]), len(fit["curve_y"]))
        self.assertAlmostEqual(sum(fit["expected"]), fit["nfit"], places=7)

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
                                     str(data), "--out-dir", str(out), "--label", "Synthetic",
                                     "--live-seconds", "1200"],
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
            self.assertEqual(result_csv[1]["Estimated"], "False")


if __name__ == "__main__":
    unittest.main()
