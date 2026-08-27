# Freezeplots

Freezeplots provides a local browser dashboard for reviewing temperature
measurements and manually annotating supercooling events for each thermocouple.

## Setup

Python 3.11 or newer is required. From the project directory, create a virtual
environment and install the project with its dashboard dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On Windows, activate the environment with `.venv\Scripts\activate` instead.

## Add data

Place the raw `.xlsx` experiment files in:

```text
data/data_raw/
```

The dashboard expects the existing experiment format: column headings on Excel
row 7, including `Date`, `Time`, and thermocouple columns.

## Run the dashboard

```bash
python dashboard.py
```

The dashboard opens in the default browser at <http://127.0.0.1:8765/>. If no
H5 cache exists, click **Create H5 file**. The generated cache is stored at
`data/data_processed/raw_data.h5` and reused on later launches.

Select an experiment and thermocouple, mark the three event points, then click
**Save/update row**. The first saved annotation creates:

```text
data/data_processed/supercooling_events_YYYY-MM-DD.csv
```

Stop the dashboard with Ctrl+C. To use another port, run for example
`python dashboard.py --port 9000`.

The dashboard can alternatively be started from `dashboard.ipynb`.
