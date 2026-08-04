import re
import warnings
import copy
import pandas as pd
import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
# from .data_funcs import *

def get_cooling_rate(df):
    """
    Get cooling rate from passed DataFrame in °C/min.

    Cooling rate is calculated using values in the range:

        0 °C < TC < 5 °C

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame with columns ["Date", "Time", "TC"].

    Returns
    -------
    float
        Cooling rate in °C/min.

    np.nan
        Returned if no suitable temperature range is found.
    """

    temp = df.loc[
        (df["TC"] > 0) & (df["TC"] < 5),
        ["Time", "TC"],
    ].copy()

    if temp.empty:
        warnings.warn(
            "No temperature values in the range 0 °C < TC < 5 °C were found.",
            UserWarning,
        )
        return np.nan

    if len(temp) < 2:
        warnings.warn(
            "Only one temperature value was found in the range "
            "0 °C < TC < 5 °C. Cooling rate cannot be calculated.",
            UserWarning,
        )
        return np.nan

    # Convert seconds to minutes
    temp["Time"] = temp["Time"] / 60

    x1 = temp["Time"].iloc[0]
    y1 = temp["TC"].iloc[0]

    x2 = temp["Time"].iloc[-1]
    y2 = temp["TC"].iloc[-1]

    if x2 == x1:
        warnings.warn(
            "The first and last time values are identical. "
            "Cooling rate cannot be calculated.",
            UserWarning,
        )
        return np.nan

    cooling_rate = (y2 - y1) / (x2 - x1)

    return cooling_rate

    
def detect_anomalies(df, threshold, window):
    """
    Detect positive temperature changes above the threshold.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame containing a 'Time' column and TC columns.
    threshold : float
        Minimum positive temperature change considered a spike.
    window : int
        Number of rows between compared temperature values.

    Returns
    -------
    dict
        Dictionary mapping each TC column to a DataFrame containing the
        spike times and temperatures.
    """
    if "Time" not in df.columns:
        raise KeyError("The DataFrame must contain a 'Time' column.")

    spike_data = {}

    tc_cols = [
        col
        for col in df.columns
        if str(col).strip().upper().startswith("TC")
    ]

    for col in tc_cols:
        temperature_change = df[col].diff(periods=window)
        spikes = temperature_change.ge(threshold).fillna(False)

        spike_data[col] = df.loc[
            spikes,
            ["Time", col]
        ].copy()

    return spike_data
    

def get_tc_columns(df):
    """
    Return thermocouple columns sorted numerically.

    Example
    -------
    TC1, TC2, TC3, ..., TC10
    """
    
    tc_cols = [
        col
        for col in df.columns
        if str(col).strip().upper().startswith("TC")
    ]

    def sort_key(col):
        match = re.search(r"\d+", str(col))
        return int(match.group()) if match else float("inf")

    return sorted(tc_cols, key=sort_key)

    
def get_first_spike_row(spikes):
    """
    Return the row containing the earliest detected spike.

    Parameters
    ----------
    spikes : pandas.DataFrame or None
        DataFrame containing a 'Time' column and one TC column.

    Returns
    -------
    pandas.Series or None
        Earliest spike row, or None when no spike exists.
    """
    if spikes is None or spikes.empty:
        return None

    valid_spikes = spikes.dropna(subset=["Time"])

    if valid_spikes.empty:
        return None

    return valid_spikes.loc[valid_spikes["Time"].idxmin()]



def get_supercooling_summary(data_dict, all_spike_times):
    """
    Create one combined first-spike and supercooling summary.
    """
    summaries = []

    for name, df in data_dict.items():
        summaries.append(
            extract_supercooling(
                df=df,
                spike_times_dict=all_spike_times[name],
                dataset_name=name,
            )
        )

    if not summaries:
        return pd.DataFrame()

    return pd.concat(
        summaries,
        ignore_index=True,
    )



def extract_supercooling(df, spike_times_dict, dataset_name):
    """
    Determine the first spike and supercooling temperature for every TC.

    The supercooling temperature is defined as the minimum temperature
    measured before the first detected spike.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame containing 'Time' and TC columns.
    spike_times_dict : dict
        Spike data returned by detect_anomalies() for one experiment.
    dataset_name : str
        Experiment name.

    Returns
    -------
    pandas.DataFrame
        One row per thermocouple.
    """
    if "Time" not in df.columns:
        raise KeyError(
            f"Dataset '{dataset_name}' does not contain a 'Time' column."
        )

    records = []

    for tc in get_tc_columns(df):
        first_spike = get_first_spike_row(
            spike_times_dict.get(tc)
        )

        # Minimum temperature across the full experiment
        min_temp_overall = df[tc].min()

        if first_spike is None:
            first_spike_time = pd.NaT
            first_spike_temperature = np.nan
            supercooling_time = pd.NaT
            supercooling_temp = np.nan
            spike_detected = False

        else:
            first_spike_time = first_spike["Time"]
            first_spike_temperature = first_spike[tc]
            spike_detected = True

            # Data strictly before the first spike
            pre_spike_data = df.loc[
                df["Time"] < first_spike_time,
                ["Time", tc],
            ].dropna(subset=[tc])

            if pre_spike_data.empty:
                supercooling_time = pd.NaT
                supercooling_temp = np.nan
            else:
                supercooling_index = pre_spike_data[tc].idxmin()

                supercooling_time = df.loc[
                    supercooling_index,
                    "Time",
                ]

                supercooling_temp = df.loc[
                    supercooling_index,
                    tc,
                ]

        records.append(
            {
                "experiment_id": dataset_name,
                "channel": tc,
                "spike_detected": spike_detected,
                "first_spike_time": first_spike_time,
                "first_spike_temperature": first_spike_temperature,
                "supercooling_time": supercooling_time,
                "supercooling_temp": supercooling_temp,
                "min_temp_overall": min_temp_overall,
            }
        )

    return pd.DataFrame(records)
