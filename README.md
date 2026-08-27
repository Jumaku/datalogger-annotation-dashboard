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

## Prepare experiment data

Before adding Excel files, update `channel_layout.json`. Each experiment ID must
contain the labels describing its thermologger channels, for example:

```json
{
  "EJ01A1": {
    "TC1": "Sample A",
    "TC2": "Sample B"
  }
}
```

Name each Excel file after its experiment ID. The filename, without `.xlsx`,
must exactly match the experiment ID in `channel_layout.json`. For the example
above, the corresponding file must be named `EJ01A1.xlsx`.

After updating the channel layout, place the raw `.xlsx` files in:

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
