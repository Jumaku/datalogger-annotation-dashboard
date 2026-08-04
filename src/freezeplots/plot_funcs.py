import plotly.graph_objects as go
import plotly.io as pio
import matplotlib as plt
import seaborn as sns
pio.renderers.default = "iframe"
from time import sleep
from .paths import APP_DIR
import json

from .eval_funcs import *

with open("channel_layout.json", "r", encoding="utf-8") as file:
    channel_layout = json.load(file)

def show_channels_by_exp(data_dict):
    
    for exp, df in data_dict.items():
        # Get all 16 thermocouple/channel columns
        channels = [col for col in df.columns if col.startswith("TC")]
        fig = go.Figure()
        
        for ch in channels:
            fig.add_trace(
                go.Scatter(
                    x=df["Time"] / 60, # get x in Minutes
                    y=df[ch],
                    mode="lines",
                    name=ch
                )
            )
        # print(exp)
        fig.update_layout(
            title=exp,
            xaxis_title="Time [min]",
            yaxis_title="Temperature [°C]",
            template="plotly_white",
            hovermode="x unified"
        )
        
        fig.show()
        sleep(1)
        fig = None


#-> if the plot is based on large data and  it does not show up go for this
# pio.renderers.default = "browser" # opens plot in browser    

def show_comp_exp(data_dict):
    fig = go.Figure()
    
    for exp, df in data_dict.items():
        channels = [col for col in df.columns if 'TC' in col]
    for ch in channels:
        for exp, df in data_dict.items():
            if ch not in df.columns: continue

            fig.add_trace(
                go.Scattergl(
                    x=df["Time"] / 60,
                    y=df[ch],
                    mode="lines",
                    name=f"{ch}_{exp}"
                )
            )

    fig.update_layout(
        title="Comparison of Experiments",
        xaxis_title="Time [min]",
        yaxis_title="Temperature [°C]",
        template="plotly_white",
        hovermode="x unified"
    )

    fig.show()



def plot_first_spikes_and_supercooling(
    df,
    spike_times_dict,
    exp="",
):
    """
    Plot all TC channels for one experiment.

    Red marker:
        First detected spike.

    Blue diamond:
        Supercooling temperature, defined as the minimum temperature
        before the first spike.
    """
    if "Time" not in df.columns:
        raise KeyError(
            f"Dataset '{exp}' does not contain a 'Time' column."
        )
    tc_cols = get_tc_columns(df)

    if not tc_cols:
        raise ValueError(
            f"Dataset '{exp}' does not contain any TC columns."
        )

    # Calculate first-spike and supercooling information for this dataset
    experiment_summary = extract_supercooling(
        df=df,
        spike_times_dict=spike_times_dict,
        dataset_name=exp,
    ).set_index("channel")

    fig = go.Figure()

    for tc in tc_cols:
        result = experiment_summary.loc[tc]

        # Full temperature trace
        fig.add_trace(
            go.Scatter(
                x=df["Time"]/60,
                y=df[tc],
                mode="lines",
                name=f"{tc} - {channel_layout[exp][tc]}",
                legendgroup=tc,
                hovertemplate=(
                    f"Channel: {tc}<br>"
                    "Time: %{x}<br>"
                    "Temperature: %{y:.3f} °C"
                    "<extra></extra>"
                ),
            )
        )

        # First-spike marker
        if result["spike_detected"]:
            fig.add_trace(
                go.Scatter(
                    x=[result["first_spike_time"]/60],
                    y=[result["first_spike_temperature"]],
                    mode="markers+text",
                    name=f"{tc} first spike",
                    legendgroup=tc,
                    showlegend=False,
                    marker={
                        "color": "red",
                        "size": 10,
                        "symbol": "circle",
                    },
                    textposition="top center",
                    hovertemplate=(
                        f"Channel: {tc}<br>"
                        "<b>First spike</b><br>"
                        "Time: %{x}<br>"
                        "Temperature: %{y:.1f} °C"
                        "<extra></extra>"
                    ),
                )
            )

        # Supercooling-temperature marker
        if pd.notna(result["supercooling_temp"]):
            fig.add_trace(
                go.Scatter(
                    x=[result["supercooling_time"]/60],
                    y=[result["supercooling_temp"]],
                    mode="markers+text",
                    name=f"{tc} supercooling",
                    legendgroup=tc,
                    showlegend=False,
                    marker={
                        "color": "blue",
                        "size": 11,
                        "symbol": "diamond",
                    },
                    textposition="bottom center",
                    hovertemplate=(
                        f"Channel: {tc}<br>"
                        "<b>Supercooling temperature</b><br>"
                        "Time: %{x}<br>"
                        "Temperature: %{y:.1f} °C"
                        "<extra></extra>"
                    ),
                )
            )

    fig.update_layout(
        title= exp,
        xaxis_title="Time",
        yaxis_title="Temperature (°C)",
        template="plotly_white",
        hovermode="closest",
        width=1200,
        height=650,
        showlegend=True,
        legend={
            "title": {"text": "TC channels"},
            "x": 1.02,
            "y": 1,
            "xanchor": "left",
            "yanchor": "top",
        },
        margin={
            "l": 70,
            "r": 170,
            "t": 80,
            "b": 60,
        },
    )

    fig.show()

    return fig
