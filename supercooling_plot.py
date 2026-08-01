mp
    """
    input_path = Path(input_path)

    if not input_path.is_file():
        raise FileNotFoundError(
            f"Input file was not found: {input_path.resolve()}"
        )

    event_df = pd.read_csv(input_path)

    required_columns = {
        "experiment_id",
        "channel",
        temperature_column,
    }

    missing_columns = required_columns.difference(
        event_df.columns
    )

    if missing_columns:
        raise ValueError(
            "The input file is missing the following required "
            f"columns: {sorted(missing_columns)}"
        )

    event_df["experiment_id"] = (
        event_df["experiment_id"]
        .astype("string")
        .str.strip()
    )

    event_df["channel"] = (
        event_df["channel"]
        .astype("string")
        .str.strip()
    )

    event_df[temperature_column] = pd.to_numeric(
        event_df[temperature_column],
        errors="coerce",
    )

    sc_df = event_df.rename(
        columns={
            temperature_column: "supercooling_temp",
        }
    )

    print(
        f"Loaded {len(sc_df)} channel records from "
        f"{input_path.resolve()}"
    )

    return sc_df


# ============================================================
# Validation
# ============================================================

def _validate_supercooling_dataframe(
    sc_df: pd.DataFrame,
) -> None:
    """
    Validate the columns required for plotting.
    """
    required_columns = {
        "experiment_id",
        "channel",
        "supercooling_temp",
    }

    missing_columns = required_columns.difference(
        sc_df.columns
    )

    if missing_columns:
        raise ValueError(
            "The DataFrame is missing the following required "
            f"columns: {sorted(missing_columns)}"
        )


def _validate_plot_sections(
    plot_sections: list[dict[str, Any]],
) -> None:
    """
    Validate the basic structure of the plot configuration.
    """
    if not isinstance(plot_sections, list):
        raise TypeError(
            "plot_sections must be a list."
        )

    if not plot_sections:
        raise ValueError(
            "plot_sections must not be empty."
        )

    for section_index, section in enumerate(
        plot_sections,
        start=1,
    ):
        if not isinstance(section, dict):
            raise TypeError(
                f"Section {section_index} must be a dictionary."
            )

        if "label" not in section:
            raise ValueError(
                f"Section {section_index} has no 'label'."
            )

        if "plots" not in section:
            raise ValueError(
                f"Section {section['label']!r} has no 'plots'."
            )

        if not isinstance(section["plots"], list):
            raise TypeError(
                f"The 'plots' entry of section "
                f"{section['label']!r} must be a list."
            )

        for plot_index, plot_definition in enumerate(
            section["plots"],
            start=1,
        ):
            if not isinstance(plot_definition, dict):
                raise TypeError(
                    f"Plot {plot_index} in section "
                    f"{section['label']!r} must be a dictionary."
                )

            if "label" not in plot_definition:
                raise ValueError(
                    f"Plot {plot_index} in section "
                    f"{section['label']!r} has no 'label'."
                )

            if "sources" not in plot_definition:
                raise ValueError(
                    f"Plot {plot_index} in section "
                    f"{section['label']!r} has no 'sources'."
                )

            if not plot_definition["sources"]:
                raise ValueError(
                    f"Plot {plot_definition['label']!r} in "
                    f"section {section['label']!r} has no sources."
                )


# ============================================================
# Data preparation
# ============================================================

def _prepare_experiment_lookup(
    sc_df: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """
    Group the DataFrame once for efficient experiment lookup.
    """
    return {
        str(experiment_id): experiment_df
        for experiment_id, experiment_df in sc_df.groupby(
            "experiment_id",
            sort=False,
        )
    }


def _extract_plot_data(
    sc_df: pd.DataFrame,
    plot_sections: list[dict[str, Any]],
    treatment_colors: dict[str, str],
) -> dict[str, Any]:
    """
    Extract boxplot values, colors, positions, and section ranges.
    """
    experiment_data = _prepare_experiment_lookup(sc_df)

    labels: list[str] = []
    temperatures: list[np.ndarray] = []
    colors: list[str] = []
    positions: list[float] = []
    section_ranges: list[dict[str, Any]] = []

    current_position = 1.0

    for section in plot_sections:
        section_label = section["label"]
        section_start = None
        section_end = None

        for plot_definition in section["plots"]:
            plot_label = plot_definition["label"]
            sources = plot_definition["sources"]

            if plot_label not in treatment_colors:
                raise ValueError(
                    f"No color has been defined for treatment "
                    f"{plot_label!r}. Add it to "
                    "TREATMENT_COLORS."
                )

            plot_color = treatment_colors[plot_label]
            combined_values: list[float] = []

            for experiment_id, channels in sources.items():
                experiment_df = experiment_data.get(
                    experiment_id
                )

                if experiment_df is None:
                    print(
                        f"Warning: experiment {experiment_id!r} "
                        f"was not found in section "
                        f"{section_label!r}."
                    )
                    continue

                if channels is None:
                    selected_df = experiment_df

                else:
                    if isinstance(channels, str):
                        selected_channels = [channels]
                    else:
                        selected_channels = list(channels)

                    available_channels = set(
                        experiment_df["channel"]
                        .dropna()
                        .astype(str)
                        .unique()
                    )

                    missing_channels = [
                        channel
                        for channel in selected_channels
                        if channel not in available_channels
                    ]

                    if missing_channels:
                        print(
                            f"Warning: experiment "
                            f"{experiment_id!r} does not contain "
                            f"channels {missing_channels}."
                        )

                    selected_df = experiment_df.loc[
                        experiment_df["channel"].isin(
                            selected_channels
                        )
                    ]

                values = (
                    selected_df["supercooling_temp"]
                    .dropna()
                    .to_numpy(dtype=float)
                )

                if len(values) == 0:
                    print(
                        f"Warning: no usable values found for "
                        f"{experiment_id!r}, channels "
                        f"{channels!r}, in section "
                        f"{section_label!r}."
                    )
                    continue

                combined_values.extend(values)

            if not combined_values:
                print(
                    f"Warning: boxplot {plot_label!r} in "
                    f"section {section_label!r} contains no "
                    "usable values."
                )
                continue

            labels.append(plot_label)

            temperatures.append(
                np.asarray(
                    combined_values,
                    dtype=float,
                )
            )

            colors.append(plot_color)
            positions.append(current_position)

            if section_start is None:
                section_start = current_position

            section_end = current_position
            current_position += 1.0

        if section_start is not None:
            section_ranges.append(
                {
                    "label": section_label,
                    "start": section_start,
                    "end": section_end,
                }
            )

            current_position += section.get(
                "gap_after",
                1.0,
            )

    if not temperatures:
        raise ValueError(
            "No supercooling-temperature values were found for "
            "the configured plot sections."
        )

    return {
        "labels": labels,
        "temperatures": temperatures,
        "colors": colors,
        "positions": positions,
        "section_ranges": section_ranges,
    }


# ============================================================
# Boxplot styling
# ============================================================

def _style_boxplots(
    boxplot_result: dict[str, list[Any]],
    colors: list[str],
    box_alpha: float,
) -> None:
    """
    Apply treatment colors to boxes, whiskers, caps, and medians.
    """
    for box, color in zip(
        boxplot_result["boxes"],
        colors,
    ):
        box.set_facecolor(color)
        box.set_edgecolor(color)
        box.set_alpha(box_alpha)
        box.set_linewidth(1.5)

    for index, color in enumerate(colors):
        first_line = index * 2
        second_line = first_line + 1

        for line_index in (
            first_line,
            second_line,
        ):
            boxplot_result["whiskers"][
                line_index
            ].set_color(color)

            boxplot_result["whiskers"][
                line_index
            ].set_linewidth(1.4)

            boxplot_result["caps"][
                line_index
            ].set_color(color)

            boxplot_result["caps"][
                line_index
            ].set_linewidth(1.4)

    for median in boxplot_result["medians"]:
        median.set_color("black")
        median.set_linewidth(1.6)


def _add_jitter_points(
    ax: Axes,
    positions: list[float],
    temperatures: list[np.ndarray],
    colors: list[str],
    *,
    seed: int,
    jitter_scale: float,
    point_size: float,
    point_alpha: float,
) -> None:
    """
    Add jittered individual measurements to each boxplot.
    """
    rng = np.random.default_rng(seed=seed)

    for position, values, color in zip(
        positions,
        temperatures,
        colors,
    ):
        x_jitter = rng.normal(
            loc=position,
            scale=jitter_scale,
            size=len(values),
        )

        ax.scatter(
            x_jitter,
            values,
            s=point_size,
            color=color,
            edgecolors="none",
            alpha=point_alpha,
            zorder=3,
        )


# ============================================================
# Section formatting
# ============================================================

def _add_section_labels(
    ax: Axes,
    section_ranges: list[dict[str, Any]],
    *,
    fontsize: float,
) -> Axes:
    """
    Add bold section labels on a secondary top x-axis.
    """
    section_centers = [
        (section["start"] + section["end"]) / 2
        for section in section_ranges
    ]

    section_labels = [
        section["label"]
        for section in section_ranges
    ]

    section_axis = ax.secondary_xaxis("top")

    section_axis.set_xticks(section_centers)

    section_axis.set_xticklabels(
        section_labels,
        fontweight="bold",
        fontsize=fontsize,
    )

    section_axis.tick_params(
        axis="x",
        length=0,
        pad=8,
    )

    return section_axis


def _add_section_separators(
    ax: Axes,
    section_ranges: list[dict[str, Any]],
) -> None:
    """
    Add vertical dashed lines between adjacent sections.
    """
    for left_section, right_section in zip(
        section_ranges[:-1],
        section_ranges[1:],
    ):
        separator_position = (
            left_section["end"]
            + right_section["start"]
        ) / 2

        ax.axvline(
            separator_position,
            linewidth=1,
            linestyle="--",
            alpha=0.3,
            zorder=0,
        )


# ============================================================
# Legend
# ============================================================

def _add_treatment_legend(
    ax: Axes,
    labels: list[str],
    colors: list[str],
    *,
    title: str,
) -> None:
    """
    Add one legend entry for each treatment used in the figure.
    """
    used_treatments: dict[str, str] = {}

    for label, color in zip(
        labels,
        colors,
    ):
        used_treatments.setdefault(
            label,
            color,
        )

    legend_handles = [
        Patch(
            facecolor=color,
            edgecolor=color,
            alpha=0.6,
            label=label,
        )
        for label, color in used_treatments.items()
    ]

    ax.legend(
        handles=legend_handles,
        title=title,
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        frameon=False,
    )


# ============================================================
# Main plotting function
# ============================================================

def plot_supercooling(
    plot_sections: list[dict[str, Any]],
    treatment_colors: dict[str, str],
    *,
    input_path: str | Path | None = None,
    sc_df: pd.DataFrame | None = None,
    output_path: str | Path | None = None,
    temperature_column: str = "start_temp_c",
    title: str = (
        "Supercooling Temperature by Experiment "
        "and Treatment"
    ),
    ylabel: str = "Supercooling temperature [°C]",
    y_range: tuple[float, float] | None = None,
    figsize: tuple[float, float] = (18, 7),
    dpi: int = 300,
    box_width: float = 0.6,
    box_alpha: float = 0.45,
    point_size: float = 21,
    point_alpha: float = 0.8,
    jitter_scale: float = 0.05,
    jitter_seed: int = 42,
    x_label_rotation: float = 90,
    tick_label_size: float = 10,
    group_label_size: float = 10,
    axis_label_size: float = 12,
    show_legend: bool = False,
    legend_title: str = "Treatment",
    show: bool = True,
) -> tuple[Figure, Axes]:
    """
    Create a grouped supercooling-temperature boxplot.

    Supply either input_path or sc_df.

    Parameters
    ----------
    plot_sections
        Ordered section and boxplot configuration.

    treatment_colors
        Dictionary mapping each treatment label to a color.

    input_path
        Path to the CSV-formatted cooling-event file.

    sc_df
        Existing standardized DataFrame. It must contain:
        experiment_id, channel, and supercooling_temp.

    output_path
        Optional path at which the figure is saved.

    y_range
        Optional ``(minimum, maximum)`` limits for the y-axis.
        Leave as ``None`` to use Matplotlib's automatic limits.

    x_label_rotation
        Rotation of the bottom x-axis tick labels in degrees.

    tick_label_size
        Font size of the x-axis and y-axis tick labels.

    group_label_size
        Font size of the bold group labels on the top axis.

    axis_label_size
        Font size of the axis labels, such as the y-axis label.

    show_legend
        Whether the treatment legend is displayed.

    show
        Whether plt.show() is called.

    Returns
    -------
    fig, ax
        The Matplotlib figure and primary axes.
    """
    if input_path is None and sc_df is None:
        raise ValueError(
            "Supply either input_path or sc_df."
        )

    if input_path is not None and sc_df is not None:
        raise ValueError(
            "Supply input_path or sc_df, not both."
        )

    _validate_plot_sections(plot_sections)

    if sc_df is None:
        sc_df = load_supercooling_data(
            input_path=input_path,
            temperature_column=temperature_column,
        )
    else:
        sc_df = sc_df.copy()

    _validate_supercooling_dataframe(sc_df)

    plot_data = _extract_plot_data(
        sc_df=sc_df,
        plot_sections=plot_sections,
        treatment_colors=treatment_colors,
    )

    labels = plot_data["labels"]
    temperatures = plot_data["temperatures"]
    colors = plot_data["colors"]
    positions = plot_data["positions"]
    section_ranges = plot_data["section_ranges"]

    fig, ax = plt.subplots(
        figsize=figsize,
        constrained_layout=True,
    )

    boxplot_result = ax.boxplot(
        temperatures,
        positions=positions,
        widths=box_width,
        showfliers=False,
        patch_artist=True,
    )

    _style_boxplots(
        boxplot_result=boxplot_result,
        colors=colors,
        box_alpha=box_alpha,
    )

    _add_jitter_points(
        ax=ax,
        positions=positions,
        temperatures=temperatures,
        colors=colors,
        seed=jitter_seed,
        jitter_scale=jitter_scale,
        point_size=point_size,
        point_alpha=point_alpha,
    )

    ax.set_xticks(positions)

    ax.set_xticklabels(
        labels,
        rotation=x_label_rotation,
        ha="center",
        fontsize=tick_label_size,
    )

    ax.tick_params(
        axis="y",
        labelsize=tick_label_size,
    )

    _add_section_labels(
        ax=ax,
        section_ranges=section_ranges,
        fontsize=group_label_size,
    )

    _add_section_separators(
        ax=ax,
        section_ranges=section_ranges,
    )

    if show_legend:
        _add_treatment_legend(
            ax=ax,
            labels=labels,
            colors=colors,
            title=legend_title,
        )

    ax.set_ylabel(
        ylabel,
        fontsize=axis_label_size,
        fontweight="bold",
    )

    if y_range is not None:
        if len(y_range) != 2:
            raise ValueError(
                "y_range must contain exactly two values: "
                "(minimum, maximum)."
            )

        y_min, y_max = y_range

        if y_min >= y_max:
            raise ValueError(
                "The lower y-axis limit must be smaller than "
                "the upper y-axis limit."
            )

        ax.set_ylim(y_min, y_max)

    ax.set_title(
        title,
        pad=45,
    )

    ax.grid(
        axis="y",
        alpha=0.3,
    )

    ax.set_xlim(
        min(positions) - 0.7,
        max(positions) + 0.7,
    )

    if output_path is not None:
        output_path = Path(output_path)

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        fig.savefig(
            output_path,
            dpi=dpi,
            bbox_inches="tight",
        )

        print(
            f"Plot saved to: {output_path.resolve()}"
        )

    if show:
        plt.show()

    return fig, ax