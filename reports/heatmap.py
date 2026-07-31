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

    # ================ DENSITY CONTOUR ================

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

    report_title = f"Density contour of animal heatmap"
    report_description = f"""
    This graph shows the density contour of animal heatmap during the
    selected time interval.
    """
    report_manager.add_report(
        name=report_title,
        html_or_figure=fig,
        top_note=report_description,
    )

    # ================ DENSITY CONTOUR HEATMAP ================
    figs = []

    for i, c in enumerate(plot_parameters["category_orders"][comparator]):
        reduce_df = df[df[comparator] == c]
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

    report_title = f"Density contour of animal heatmap"
    report_description = f"""
    This graph shows the density contour of animal heatmap for each animal
    during the selected time interval. The color of the heatmap lines
    represents the density of detections in this area, with darker and lighter
    colors representing respectively a higher and a lower density values.
    """

    report_manager.add_multi_fig_report(
        name=report_title,
        figures=figs,
        top_note=report_description,
        max_fig_in_row=2,
    )

    # ================ DENSITY HEATMAP LOG SCALE ================
    counts, x_edges, y_edges = np.histogram2d(df["X"], df["Y"], bins=50)
    log_counts = np.log1p(counts.T)
    raw_ticks = [0, 1, 5, 10, 50, 100, 500, 1000, int(counts.max())]
    raw_ticks = sorted({v for v in raw_ticks if v <= counts.max()})
    fig = go.Figure(
        go.Heatmap(
            x=(x_edges[:-1] + x_edges[1:]) / 2,
            y=(y_edges[:-1] + y_edges[1:]) / 2,
            z=log_counts,
            colorbar=dict(
                title="Count",
                tickvals=np.log1p(raw_ticks),
                ticktext=[str(v) for v in raw_ticks],
            ),
        )
    )
    fig.update_layout(
        xaxis=dict(
            title="X position (<i>cm</i>)",
        ),
        yaxis=dict(
            title="Y position (<i>cm</i>)",
        ),
        title="Density heatmap",
        plot_bgcolor="rgba(0,0,0,0)",
    )

    # ================ TABLE ================
    report_manager.add_table_headers(name="complete table", df=df)
