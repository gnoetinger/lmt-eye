"""
@author: xmousset
"""

import logging

import pandas as pd
import plotly.express as px

from scripts.reports_manager import HTMLReportManager
from scripts.settings import AnalysisSettings
from scripts.plotting_functions import (
    draw_nights,
    line_with_shade,
)


def generic_reports(
    report_manager: HTMLReportManager,
    df: pd.DataFrame | None,
    settings: AnalysisSettings,
):
    """Get all sensors datas in a dataframe using the given dataframe and
    construct all the generic reports into the given `HTMLReportManager`.
    """

    report_manager.reports_creation_focus("Sensors")

    if df is None:
        logging.warning("No sensors data available. Creating empty report.")
        report_manager.add_report(
            name="Sensors data not available",
            html_or_figure="""
            No sensors data available in this dataset.
            """,
        )
        return None

    # ================ PARAMETERS ================

    X_axis = settings.report_x_axis

    NB_MIN_PER_BIN = settings.time_window / settings.fps / 60

    # if settings.bin_rounding:
    #     df = df[df["START_FRAME"] != df["START_FRAME"].iloc[0]]

    nights_parameters = {
        "start_time": df["START_TIME"].min(),
        "end_time": df["END_TIME"].max(),
        "night_begin": settings.night_begin,
        "night_duration": settings.night_duration,
    }

    sensors = [
        "TEMPERATURE",
        "HUMIDITY",
        "SOUND",
        "LIGHTVISIBLE",
        "LIGHTVISIBLEANDIR",
    ]
    sensors_labels = [
        "Temperature",
        "Humidity",
        "Sound",
        "Light visible",
        "Light visible + IR",
    ]
    units = [
        "°C",
        "%",
        "?",
        "?",
        "?",
    ]

    # ================ TITLES ================

    report_manager.add_title(
        name=f"Sensors data visualization",
        content=f"""
        This section presents the visualization of the sensors data recorded in
        the dataset. All sensors data can be downloaded in Excel format by
        clicking on the '<i>Download data</i>' link in the top-right hand
        corner of the last report (<i>complete table</i>).""",
    )

    report_manager.add_card(
        name="Time interval unit",
        content=f"""
        Calculated time bin is {settings.time_window} frames.
        <br>It corresponds to {NB_MIN_PER_BIN:.1f} minutes.
        """,
    )
    report_manager.add_card(
        name="Sensors units",
        content="?",
    )

    # ================ SENSORS OVERVIEW CARD ================

    card = """<div style="flex: 0 0 320px; min-width: 220px;
    max-width: 400px;"> <div style="margin:0; padding:0;">
    """
    for sensor, label, unit in zip(sensors, sensors_labels, units):
        if (
            sensor + "_MEAN" not in df.columns
            or df[sensor + "_MEAN"].isnull().all()
        ):
            card += (
                f"<p style='margin: 0.5em 0;'>{label} data not available</p>"
            )
        else:
            mean = round(df[sensor + "_MEAN"].mean(), 2)
            std = round(df[sensor + "_MEAN"].std(), 2)
            card += (
                f"<p style='margin: 0.5em 0;'>{label} : "
                f"<strong>{mean}</strong> "
                f"<span>&plusmn;</span> {std} {unit}</p>"
            )
    card += "</div></div>"

    report_manager.add_card(
        name="Sensors",
        content=card,
    )

    # ================ SENSORS PLOTS ================

    for sensor, sensor_label, unit in zip(sensors, sensors_labels, units):

        mean_col = f"{sensor}_MEAN"
        min_col = f"{sensor}_MIN"
        max_col = f"{sensor}_MAX"

        if mean_col in df.columns:
            fig = line_with_shade(
                df,
                X_axis,
                mean_col,
                y_min_col=min_col,
                y_max_col=max_col,
            )
            fig = draw_nights(fig, **nights_parameters)

            fig.update_layout(
                title=f"{sensor_label} over time",
                yaxis_title=f"{sensor_label} ({unit})",
                xaxis_title=f"Time ({X_axis})",
            )

            report_title = f"{sensor_label} mean with min and max"
            report_description = f"""
            {sensor_label} mean ({mean_col}) with the minimum and maximum as
            the shaded area ({min_col}, {max_col}) over time ({X_axis}).<br>
            """
            if sensor == "LIGHTVISIBLE":
                report_description += """
                This graph allows a visualization of the Day and Night cycle
                between what is expected (grey bands) and what the sensors
                recorded (line with shaded area).
                """

            report_manager.add_report(
                name=report_title,
                html_or_figure=fig,
                top_note=report_description,
                graph_datas=df[
                    [
                        X_axis,
                        "END_TIME",
                        mean_col,
                        min_col,
                        max_col,
                    ]
                ],
            )
        else:
            report_manager.add_report(
                name=f"{sensor_label} data not available",
                html_or_figure=f"""
                No data available for {sensor} sensor in this dataset.
                """,
            )

    # ================ TABLE ================
    report_manager.add_table_headers(name="complete table", df=df)
