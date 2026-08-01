from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROC_DATA_DIR = PROJECT_ROOT / "data" / "data_processed"
RAW_DATA_DIR = PROJECT_ROOT / "data" / "data_raw"
OUTPUT_DIR = PROJECT_ROOT / "output"
PLOT_DIR = OUTPUT_DIR / "plots"
CHANNEL_LAYOUT_PATH = PROJECT_ROOT / "channel_layout.json"