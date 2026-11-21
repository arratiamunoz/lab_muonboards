# CAEN A5202 bench analysis

Read-only analysis of archived JANUS list-mode CSVs. Reproduces the Run 16 high-gain and low-gain pulse-height spectra and Minuit2 MIP-like peak fits for channels 0–15. No run data or hardware-control code is included.

## Run

Use Python 3.12 or newer in a virtual environment.

```sh
python -m pip install -r requirements.txt
python analysis/adc_mip.py /path/to/Run16_list.csv --out-dir results --label "Run 16"
python -m unittest discover -s tests -v
```

The input needs `Trg_Id,Board_Id,CH_Id,PHA_HG,PHA_LG` columns and decimal ADC codes. Choose the board with `--board` (default 0). Supply `--live-seconds SECONDS` for the saved-trigger-rate label and `--setup TEXT` to add the verified gain, thresholds and bias setpoint. Use `--spectra-only` to skip fitting or adjust `--spectra-ymax` and `--fits-ymax` to change the linear display limits without changing the data or fits.

## Outputs

- `adc_spectra.{png,pdf}`: both gains on the full 0–8192 ADC range, 64 ADC per bin, with asymmetric central 68.27% Garwood count intervals. Zero counts are omitted from the display; triangles mark groups of off-scale bins.
- `mip_fitted_spectra.{png,pdf}`: Landau–Gaussian signal plus flat background, fitted with iminuit/Minuit2 and a binned Poisson deviance. Expected counts are integrated over each bin, including zero bins within the fit windows. Separate HG/LG windows exclude the pedestal and ADC rail. When the fitted Landau width remains at its lower bound after a finer-grid refit, try the nested Gaussian limit.
- `mip_mpv_by_channel.{png,pdf}`: maximum of the convolved signal, not the unconvolved Landau location, with statistical uncertainties and gray lines showing the range of MPVs across windows and, for Gaussian-limit fits, both peak shapes. Both vertical axes start at zero. The mean and relative population spread use every finite MPV.
- `mip_fit_results.csv`: MPVs, asymmetric statistical intervals, fit variation, windows, and diagnostics. The initial fit uses three starts and two alternate windows. For flagged fits, a finer-grid refit relaxes the background cap and Landau width floor, and MINOS profiles the MPV when it converges. Other statistical intervals use Hesse covariance. A nominal fit window needs at least 20 entries.

The fit windows are tuned for the Run 16 HG/LG response; validate the chosen windows before analyzing data with different gain settings. The tests use synthetic data only.

Method references: [ROOT Landau–Gaussian fit](https://root.cern/doc/master/langaus_8C.html), [iminuit binned-fit examples](https://scikit-hep.org/iminuit/notebooks/binned_vs_unbinned.html).
