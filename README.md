# Freeze

Python and Jupyter tooling for analyzing freeze experiment thermocouple data.
The project loads raw Excel logger files, normalizes thermocouple channel names,
trims experiments by elapsed time, detects temperature spikes, estimates
supercooling temperatures, and generates interactive or static plots.

## Project Layout

| Path | Purpose |
| --- | --- |
| `main.ipynb` | Main analysis notebook. Loads data, selects experiments, computes cooling and supercooling metrics, and produces plots. |
| `manual_supercooling_dashboard.ipynb` | Focused notebook for loading `data/data_raw/raw_data.h5` and manually annotating spike start, spike maximum, and spike end for each thermocouple channel. |
| `manual_supercooling_cells.ipynb` | Non-widget manual annotation notebook for frontends that do not render `ipywidgets`; edit normal Python variables and run cells to plot/save events. |
| `manual_supercooling_click_dashboard.ipynb` | Local click dashboard: choose experiment/channel, click three event points, mark no-clear events, and persist the annotations table. |
| `src/freezeplots/data_funcs.py` | Data loading and persistence helpers for Excel and HDF5 workflows. |
| `src/freezeplots/eval_funcs.py` | Analysis helpers for cooling rate, spike detection, thermocouple sorting, and supercooling summaries. |
| `src/freezeplots/plot_funcs.py` | Plotly visualization helpers for channel traces, experiment comparisons, and spike/supercooling markers. |
| `src/freezeplots/paths.py` | Central path configuration used by the notebooks and package modules. |
| `channel_layout.json` | Experiment-specific mapping from `TC` channels to sample or treatment labels. |
| `data/data_raw/` | Raw experiment Excel files such as `EJ01A1.xlsx` through `EJ42B1.xlsx`. |
| `output/` | Generated CSV data and static plot outputs. |
| `scripts/iframe_figures/` | Plotly iframe HTML outputs created by notebook rendering. |

## Data Model

Raw input files are expected to be Excel workbooks with data beginning after a
six-row header block. `setup_data_dict()` reads these files with
`pandas.read_excel(..., header=6)`.

During loading:

1. Columns containing `Thermo` are renamed to `TC` channel names.
2. `Time` is converted from timestamps to elapsed seconds from the first row.
3. `Date` is parsed as datetimes and used as the DataFrame index.
4. Each experiment is stored in a dictionary keyed by experiment ID, for example
   `data_dict["EJ33B1"]`.

Most analysis functions expect each experiment DataFrame to contain:

- `Time`: elapsed seconds.
- `Date`: timestamp column.
- `TC1`, `TC2`, ...: thermocouple temperature columns.

## Environment

This project is a notebook/script workflow and does not currently include a
package manifest. Install the Python packages used by the modules and notebook:

```bash
python -m pip install pandas numpy scipy matplotlib seaborn plotly ipywidgets openpyxl tables jupyter
```

`ipywidgets` is needed for the manual annotation dashboard in `main.ipynb`.
`tables` is needed for the optional HDF5 cache helpers that use
`pandas.HDFStore`.

## Path Configuration

`src/freezeplots/paths.py` derives the project root from the installed source
file, so the repository can be moved without editing a hard-coded path. It also
provides the legacy `APP_DIR` mapping used by the exploratory notebooks:

- `APP_DIR["data"]`: raw Excel input directory.
- `APP_DIR["procdata"]`: processed data directory.
- `APP_DIR["scripts"]`: scripts directory.
- `APP_DIR["output"]`: output directory.

## Typical Workflow

1. Open `main.ipynb` in Jupyter.
2. Choose experiments by setting `TARGET_EXP`, for example:

   ```python
   TARGET_EXP = ["EJ33B1"]
   # or
   TARGET_EXP = ["All"]
   ```

3. Choose an elapsed-time trim window:

   ```python
   CUTOFF_BEG = "20min"
   CUTOFF_END = "300min"
   ```

4. Load and trim data:

   ```python
   data_dict = setup_data_dict(TARGET_EXP)

   for exp, df in data_dict.items():
       data_dict[exp] = cut_elapsed(df, beg=CUTOFF_BEG, end=CUTOFF_END)
   ```

5. Inspect channels:

   ```python
   show_channels_by_exp(data_dict)
   show_comp_exp(data_dict)
   ```

6. Detect freezing spikes and summarize supercooling temperatures:

   ```python
   threshold = 0.2
   window = 10

   all_spike_times = {
       name: detect_anomalies(df=df, threshold=threshold, window=window)
       for name, df in data_dict.items()
   }

   sc_df = get_supercooling_summary(
       data_dict=data_dict,
       all_spike_times=all_spike_times,
   )
   ```

7. Plot first spikes and supercooling markers:

   ```python
   fig = plot_first_spikes_and_supercooling(
       df=data_dict["EJ33B1"],
       spike_times_dict=all_spike_times["EJ33B1"],
       exp="EJ33B1",
   )
   ```

8. Export summaries or figures from the notebook as needed.

## Main Analysis Functions

| Function | Location | Description |
| --- | --- | --- |
| `setup_data_dict()` | `src/freezeplots/data_funcs.py` | Loads selected raw Excel files into a dictionary of DataFrames. |
| `cut_elapsed()` | `src/freezeplots/data_funcs.py` | Filters a DataFrame to an elapsed-time window from the first timestamp. |
| `save_data_dict_hdf()` | `src/freezeplots/data_funcs.py` | Saves experiment DataFrames to an HDF5 file. |
| `load_data_dict_hdf()` | `src/freezeplots/data_funcs.py` | Loads an HDF5 experiment dictionary. |
| `get_cooling_rate()` | `src/freezeplots/eval_funcs.py` | Calculates cooling rate in `deg C/min` using values between `0` and `5 deg C`. |
| `detect_anomalies()` | `src/freezeplots/eval_funcs.py` | Detects positive temperature jumps above a threshold over a row window. |
| `extract_supercooling()` | `src/freezeplots/eval_funcs.py` | Finds the first spike and minimum pre-spike temperature for each thermocouple. |
| `get_supercooling_summary()` | `src/freezeplots/eval_funcs.py` | Combines per-experiment supercooling summaries into one DataFrame. |
| `show_channels_by_exp()` | `src/freezeplots/plot_funcs.py` | Shows all thermocouple traces for each experiment. |
| `show_comp_exp()` | `src/freezeplots/plot_funcs.py` | Compares matching thermocouple channels across experiments. |
| `plot_first_spikes_and_supercooling()` | `src/freezeplots/plot_funcs.py` | Plots traces with first-spike and supercooling markers. |

## Outputs

Current generated artifacts include:

- CSV exports in `output/data/`.
- PNG plots in `output/plots/`.
- Plotly iframe HTML files in `scripts/iframe_figures/`.

The notebook also includes examples for writing supercooling summaries to Excel,
for example `sc_df.to_excel(...)`.

The click dashboard includes a raw-data sync card. It compares `.xlsx` files in
`data/data_raw/` with experiments already stored in `data/data_raw/raw_data.h5`
and can append missing experiments to the HDF5 file.

## Notes

- The repository includes notebook checkpoint and Python bytecode directories
  (`.ipynb_checkpoints/`, `__pycache__/`). These are generated artifacts and are
  not required to understand the analysis.
- Some notebook cells are exploratory and assume particular experiments or
  channels are already loaded. Run the notebook from the top after confirming
  `TARGET_EXP`, channel drops, and path configuration.
- Spike detection is threshold-based. The notebook comments note that
  `threshold = 0.4`, `window = 5` worked for non-smoothed data, while
  `threshold = 0.2`, `window = 10` was used for smoothed data.
