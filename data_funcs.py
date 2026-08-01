import os
from os import path
import pandas as pd
import numpy as np
import matplotlib as plt
import seaborn as sns
import datetime as dt
import plotly.graph_objects as go
import plotly.io as pio
from time import sleep
from pprint import pprint
from freeze_paths import APP_DIR

from pathlib import Path
#TODO maybe change that
# from eval_funcs import *


def rename_df(df): 
    rename_dct = {}
    for col in df.columns:
        rename_dct[col] = col 
        if 'Thermo' in col:
            rename_dct[col] = 'TC' + col.split()[1]
    df.rename(columns=rename_dct, inplace=True)    
    return df

def convert_time(df):
    df['Time'] = pd.to_datetime(df['Time'])
    df['Time'] = (df['Time'] - df['Time'].iloc[0]).dt.total_seconds()    
    df.Date = pd.to_datetime(df['Date'])
    df = df.set_index(df['Date'])
    return df
    
def setup_data_dict(TARGET_EXP:list):
    data_dict = {}
    for exp in sorted(os.listdir(APP_DIR['data'])):
        if exp[0] == '.' : continue
  
        name_exp = exp.split('.')[0]
        file_type = exp.split('.')[1]
        if file_type != 'xlsx': continue
        
        if (name_exp in TARGET_EXP) or ('All' in TARGET_EXP):
            df_path = path.join(APP_DIR['data'], exp)
            print(df_path)
            df = pd.read_excel( df_path, header=6 )
            
            # Renaming 'Thermocouple' headers to TC
            df = rename_df(df)
    
            # Convert Time column to seconds
            df = convert_time(df)
            
            # Assign df to data dirct
            data_dict[str(name_exp)] = df
    
    return data_dict

def cut_elapsed(df: pd.DataFrame, beg=None, end=None):
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])

    start = df["Date"].min()
    mask = pd.Series(True, index=df.index)

    if beg is not None:
        mask &= df["Date"] >= start + pd.to_timedelta(beg)

    if end is not None:
        mask &= df["Date"] <= start + pd.to_timedelta(end)

    return df.loc[mask]


def save_data_dict_hdf(data_dict, filename="raw_data.h5"):
    with pd.HDFStore(
        filename,
        mode="w",
        complevel=5,
        complib="blosc",
    ) as store:
        for name, df in data_dict.items():
            store.put(
                key=name,
                value=df,
                format="fixed",
            )

def load_data_dict_hdf(filename="raw_data.h5"):
    with pd.HDFStore(filename, mode="r") as store:
        return {
            key.lstrip("/"): store[key]
            for key in store.keys()
        }


import warnings
import pandas as pd


def update_hdf5_from_dict(data_dict, hdf5_path):
    """
    Add all DataFrames from data_dict to an HDF5 file.

    Existing keys are not overwritten. They are skipped with a warning.

    Parameters
    ----------
    data_dict : dict[str, pd.DataFrame]
        Dictionary where each key becomes the HDF5 dataset name.

    hdf5_path : str
        Complete path to the HDF5 file, including the filename.
    """
    added = []
    skipped = []

    with pd.HDFStore(hdf5_path, mode="a") as store:
        existing_keys = set(store.keys())

        for key, df in data_dict.items():
            hdf_key = f"/{key.lstrip('/')}"

            if hdf_key in existing_keys:
                warnings.warn(
                    f"Key {key!r} already exists in {hdf5_path}. Skipping it.",
                    UserWarning,
                )
                skipped.append(key)
                continue

            if not isinstance(df, pd.DataFrame):
                warnings.warn(
                    f"Value for key {key!r} is not a DataFrame. Skipping it.",
                    UserWarning,
                )
                skipped.append(key)
                continue

            store.put(
                key=key,
                value=df,
                format="fixed",
            )

            added.append(key)
            existing_keys.add(hdf_key)

    print(f"Added: {len(added)} DataFrame(s)")
    print(f"Skipped: {len(skipped)} DataFrame(s)")

    return {
        "added": added,
        "skipped": skipped,
    }