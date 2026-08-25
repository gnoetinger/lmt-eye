"""
@author: xmousset
"""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from scripts.reports_manager import HTMLReportManager
from scripts.settings import AnalysisSettings

COLOR_MAP = px.colors.qualitative.Plotly


def _count_tick_values(max_count: int) -> list[int]:
    """Return readable count labels for a logarithmic colourbar."""
    if max_count <= 10:
        return list(range(max_count + 1))

    tick_values = [0]
    magnitude = 1
    while magnitude <= max_count:
        for base in (1, 2, 5):
            value = base * magnitude
            if value <= max_count:
                tick_values.append(value)
        magnitude *= 10

    return tick_values


def _log_count_colorbar(max_count: int) -> dict[str, object]:
    """Map raw count labels to the log1p values plotted in a heatmap."""
    count_ticks = _count_tick_values(max_count)
    return {
        "title": "Count",
        "tickvals": np.log1p(count_ticks),
        "ticktext": [str(count) for count in count_ticks],
    }


def _heatmap_figure(
    data: pd.DataFrame,
    density_column: str,
    title: str,
    colorbar: dict[str, object],
) -> go.Figure:
    """Create a spatial density heatmap with consistently scaled axes."""
    fig = go.Figure(
        go.Heatmap(
            x=data["X"],
            y=data["Y"],
            z=data[density_column],
            colorbar=colorbar,
        )
    )
    fig.update_layout(
        xaxis=dict(
            title="X position (<i>cm</i>)",
            scaleanchor="y",
            scaleratio=1,
        ),
        yaxis=dict(title="Y position (<i>cm</i>)"),
        title=title,
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def generic_reports(
    report_manager: HTMLReportManager,
    df: pd.DataFrame | None,
    settings: AnalysisSettings,
):
    """Analyse animal heatmap and creates a generic dataframe using the given
    `DataFrameConstructor` and construct all the generic reports into the given
    `HTMLReportManager` and returning the generated dataframe."""

    report_manager.reports_creation_focus("Heatmap")

    if df is None:
        report_manager.add_title(
            name="Analysis of animal heatmap",
            content="""
            No data available for the selected time interval. Please adjust
            the processing limits or check the database connection.""",
        )
        return None

    df["MIN_FROM_START"] = df["FRAME"] / settings.fps / 60

    # ================ PARAMETERS ================

    comparator = settings.report_color
    plot_parameters = settings.get_plot_parameters(df)

    # ================ HEATMAP CALCULATION ================

    min_value = int(np.floor(min(df["X"].min(), df["Y"].min())))
    max_value = int(np.ceil(max(df["X"].max(), df["Y"].max())))
    bin_edges = np.arange(min_value, max_value + 1)
    _, x_edges, y_edges = np.histogram2d(
        df["X"],
        df["Y"],
        bins=bin_edges,
    )
    heatmap_x = (x_edges[:-1] + x_edges[1:]) / 2
    heatmap_y = (y_edges[:-1] + y_edges[1:]) / 2
    heatmap_df_per_rfid = []
    for rfid, df_rfid in df.groupby("RFID"):
        rfid_counts, _, _ = np.histogram2d(
            df_rfid["X"],
            df_rfid["Y"],
            bins=[x_edges, y_edges],
        )
        rfid_log_counts = np.log1p(rfid_counts.T)
        heatmap_df_per_rfid.append(
            pd.DataFrame(
                [
                    {
                        "RFID": rfid,
                        "X": x,
                        "Y": y,
                        "Density": rfid_counts.T[i, j],
                        "Density_log": rfid_log_counts[i, j],
                    }
                    for i, y in enumerate(heatmap_y)
                    for j, x in enumerate(heatmap_x)
                ]
            )
        )

    heatmap_df = pd.concat(heatmap_df_per_rfid, ignore_index=True)

    # ================ TITLES ================

    report_manager.add_title(
        name=f"Analysis of animal heatmap",
        content=f"""
        This section presents the analysis of animal heatmap recorded in the
        dataset. You <b>CANNOT</b> download the underlying data used for the
        plots because the data are not binned.""",
    )

    report_manager.add_card(
        name="Distance unit",
        content="All distances are in centimeters (<i>cm</i>).",
    )

    df_count = df.groupby("RFID").size().reset_index(name="Count")
    detections_content = "<br>".join(
        f"{rfid}: {count:,} frames".replace(",", " ")
        for rfid, count in zip(df_count["RFID"], df_count["Count"])
    )
    report_manager.add_card(
        name="Detections",
        content=(
            "Number of frames where each animal was detected:<br>"
            f"{detections_content}"
        ),
    )

    # ================ ALL DENSITY CONTOUR ================

    fig = px.density_contour(
        df,
        x="X",
        y="Y",
        marginal_x="histogram",
        marginal_y="histogram",
        labels={"X": "X position (<i>cm</i>)", "Y": "Y position (<i>cm</i>)"},
        **plot_parameters,
    )
    fig.update_layout(
        height=600,
        xaxis=dict(scaleanchor="y", scaleratio=1),
        yaxis=dict(scaleanchor="x", scaleratio=1),
    )

    report_title = f"All density contour of animals"
    report_description = f"""
    This graph shows the density contour of animals during the selected time
    interval.
    """
    report_manager.add_report(
        name=report_title,
        html_or_figure=fig,
        top_note=report_description,
    )

    # ================ DENSITY CONTOUR PER ANIMAL ================
    figs = []

    for i, c in enumerate(plot_parameters["category_orders"][comparator]):
        reduce_df = df[df[comparator] == c]  # type: ignore
        fig = px.density_contour(
            reduce_df,
            x="X",
            y="Y",
            color_discrete_sequence=[COLOR_MAP[i]],
            labels={
                "X": "X position (<i>cm</i>)",
                "Y": "Y position (<i>cm</i>)",
            },
        )
        fig.update_traces(
            contours_coloring="fill",
            contours_showlines=False,
            selector=dict(type="histogram2dcontour"),
            colorscale="Blues",
        )
        fig.update_layout(
            margin=dict(l=0, r=0, t=30, b=0),
            xaxis=dict(scaleanchor="y", scaleratio=1),
            yaxis=dict(scaleanchor="x", scaleratio=1),
            showlegend=False,
            title=f"{comparator}: {c}",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        figs.append(fig)

    report_title = f"Density contour per animal"
    report_description = f"""
    This graph shows the density contour for each animal during the selected
    time interval. The color of the heatmap lines represents the density of
    detections in this area, with darker and lighter colors representing
    respectively a higher and a lower density values.
    """

    report_manager.add_multi_fig_report(
        name=report_title,
        figures=figs,
        top_note=report_description,
        max_fig_in_row=2,
    )

    # ================ ALL DENSITY HEATMAP ================
    figs = []

    all_heatmap_df = heatmap_df.groupby(["X", "Y"], as_index=False)[
        "Density"
    ].sum()
    all_heatmap_df["Density_log"] = np.log1p(all_heatmap_df["Density"])

    # linear scale
    # ----------------
    fig = _heatmap_figure(
        all_heatmap_df,
        density_column="Density",
        title="Density heatmap (linear scale)",
        colorbar={"title": "Count"},
    )
    figs.append(fig)

    # log scale
    # ----------------
    max_density = int(all_heatmap_df["Density"].max())

    fig = _heatmap_figure(
        all_heatmap_df,
        density_column="Density_log",
        title="Density heatmap (log scale)",
        colorbar=_log_count_colorbar(max_density),
    )
    figs.append(fig)

    report_title = "Density heatmap"
    report_description = f"""
    These graphs show the density heatmap of animals during the selected time
    interval. The color of the heatmap represents the density of detections
    in this area, with darker and lighter colors representing respectively
    a higher and a lower density values. One graph is in linear scale and the
    other one is in log scale to better visualize the density distribution.
    """

    report_manager.add_multi_fig_report(
        name=report_title,
        figures=figs,
        top_note=report_description,
        max_fig_in_row=2,
        graph_datas=all_heatmap_df[["X", "Y", "Density", "Density_log"]],
    )

    # ================ DENSITY HEATMAP PER ANIMAL ================
    figs = []

    for i, c in enumerate(plot_parameters["category_orders"][comparator]):
        reduce_df = heatmap_df[heatmap_df[comparator] == c]
        fig = _heatmap_figure(
            reduce_df,
            density_column="Density",
            title=f"{comparator}: {c}",
            colorbar={"title": "Count"},
        )
        figs.append(fig)

    report_title = f"Density heatmap per animal"
    report_description = f"""
    This graph shows the density heatmap for each animal during the selected
    time interval. The color of the heatmap represents the density of
    detections in this area, with darker colors representing higher density values.
    """

    report_manager.add_multi_fig_report(
        name=report_title,
        figures=figs,
        top_note=report_description,
        max_fig_in_row=2,
        graph_datas=heatmap_df[[comparator, "X", "Y", "Density"]],
    )

    # =============== DENSITY HEATMAP PER ANIMAL (LOG SCALE) ================
    figs = []

    for i, c in enumerate(plot_parameters["category_orders"][comparator]):
        reduce_df = heatmap_df[heatmap_df[comparator] == c]
        max_density = int(reduce_df["Density"].max())
        fig = _heatmap_figure(
            reduce_df,
            density_column="Density_log",
            title=f"{comparator}: {c} (log scale)",
            colorbar=_log_count_colorbar(max_density),
        )
        figs.append(fig)

    report_title = f"Density heatmap per animal (log scale)"
    report_description = f"""
    This graph shows the density heatmap for each animal during the selected
    time interval on a log scale. The color of the heatmap represents the density of
    detections in this area, with darker colors representing higher density values.
    """

    report_manager.add_multi_fig_report(
        name=report_title,
        figures=figs,
        top_note=report_description,
        max_fig_in_row=2,
        graph_datas=heatmap_df[[comparator, "X", "Y", "Density_log"]],
    )

    # ================ TABLE ================
    # report_manager.add_table_headers(name="complete table", df=df)
    report_manager.add_table_headers(name="complete table", df=heatmap_df)
