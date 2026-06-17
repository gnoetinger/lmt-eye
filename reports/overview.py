"""
@author: xmousset
"""

import logging
from typing import List

import pandas as pd

from scripts.reports_manager import HTMLReportManager
from scripts.settings import AnalysisSettings, ComparisonSettings
from scripts.plotting_functions import str_h_min


def generic_reports(
    report_manager: HTMLReportManager,
    df_animals: pd.DataFrame | None,
    df_activity: pd.DataFrame | None,
    df_events: pd.DataFrame | None,
    df_sensors: pd.DataFrame | None,
    settings: AnalysisSettings | ComparisonSettings,
):
    """This function uses the provided report manager to create a structured
    summary of the experiment, including cards for experiment details, animal
    activity, analyzed events, and sensor readings."""

    report_manager.reports_creation_focus("main")
    if df_animals is None:
        report_manager.add_title(
            name="Overview analysis",
            content="No data available.",
        )
        return None

    # ================ PARAMETERS ================
    NB_ANIMALS = df_animals["RFID"].nunique()
    if df_activity is not None:
        EXP_DURATION = (
            df_activity["END_TIME"].max() - df_activity["START_TIME"].min()
        ).total_seconds()
        NB_DAYS = EXP_DURATION / 3600 / 24
    else:
        EXP_DURATION = 0
        NB_DAYS = 0

    if isinstance(settings, AnalysisSettings):
        if settings.database_path is None:
            EXP_NAME = "Unknown experiment"
        else:
            EXP_NAME = settings.database_path.stem
        title_msg = f"""
        This is a summary of the <i>{EXP_NAME}</i> dataset
        analysis. As a reminder, if you want to compare this analysis
        with another one, it is better if they have the same binning
        size.
        """
    else:
        EXP_NAME = (
            "Comparison of analyses\nComparator: " + settings.report_color
        )
        title_msg = f"""
        This is a summary of the comparison between analyses. The
        comparator used for this comparison is 
        <strong>{settings.report_color}</strong>. All analyses included in this
        comparison are listed in the settings table at the end of this report.
        """

    # ================ TITLES ================
    report_manager.add_title(
        name=EXP_NAME,
        content=f"""
        <div style="width:80%; margin: 0 auto; text-align: center;">
            <div style="margin-bottom:1em;">
                {title_msg}
                <hr>
            </div>
        </div>
        <style>
            table.dataframe {{
                border-collapse: collapse;
                border: 2px solid #fff;
            }}
            table.dataframe th, table.dataframe td {{
                border: none;
                padding: 8px;
                text-align: center;
            }}
            table.dataframe th {{
                font-weight: bold;
            }}
        </style>
        <center>{df_animals.to_html(index=False, border=1)}</center>
        """,
    )

    # ================ CARD: EXPERIMENT ================
    if df_activity is not None:
        exp_duration_str = f"""
            <p style="margin: 0.5em 0;">Run during 
            <strong>{NB_DAYS:1.1f} days</strong> 
            and 
            <strong>{EXP_DURATION // 3600} hours</strong> 
            and 
            <strong>{(EXP_DURATION // 60) % 60} minutes</strong>
            </p>
        """
    else:
        exp_duration_str = """
            <p style='margin: 0.5em 0;'>
            Experiment duration not available (need activity analysis).
            </p>
        """
    card = f"""
        <div style="flex: 0 0 320px; min-width: 220px; max-width: 400px;">
            <div style="margin:0; padding:0;">
                <p style="margin: 0.5em 0;">Include 
                <strong>{NB_ANIMALS} animals</strong>
                </p>
                {exp_duration_str}
        """
    if isinstance(settings, AnalysisSettings):
        if df_activity is not None:
            start_end_str = f"""
                <p style="margin: 0.5em 0;">
                {df_activity["START_TIME"].min().floor("s")} - start
                </p>
                <p style="margin: 0.5em 0;">
                {df_activity["END_TIME"].max().floor("s")} - end
                </p>
            """
        else:
            start_end_str = """
                <p style='margin: 0.5em 0;'>
                Start and end times not available (need activity analysis).
                </p>
            """
        card += f"""
                <p style="margin: 0.5em 0;">Binned every <strong>
                {settings.time_window / settings.fps / 60} minutes
                </strong></p>
                {start_end_str}
            """
    card += """
            </div>
        </div>
    """

    report_manager.add_card(
        name=f"Experiment informations",
        content=card,
    )

    # ================ CARD: ACTIVITY ================
    if isinstance(settings, AnalysisSettings):
        if df_activity is not None:

            card = get_activity_card(
                df_activity,
                NB_ANIMALS,
                NB_DAYS,
                settings,
            )

            report_manager.add_card(
                name="Animal Average Activity",
                content=card,
            )
        else:
            report_manager.add_card(
                name="Animal Average Activity",
                content="<p>No activity analysed.</p>",
            )

    # ================ CARD: EVENTS ================
    if df_events is not None:

        overview_event_list = df_events["EVENT"].unique().tolist()

        card = get_event_card(
            df_events,
            overview_event_list,
            NB_ANIMALS,
            NB_DAYS,
        )

        report_manager.add_card(
            name="Animal Average Events",
            content=card,
        )
    else:
        report_manager.add_card(
            name="Animal Average Events",
            content="<p>No event analysed.</p>",
        )

    # ================ CARD: SENSORS ================
    if df_sensors is not None:

        card = get_sensors_card(df_sensors)

        report_manager.add_card(
            name="Average Sensors",
            content=card,
        )
    else:
        if isinstance(settings, AnalysisSettings):
            report_manager.add_card(
                name="Average Sensors",
                content="<p>No sensor data available.</p>",
            )
        else:
            if df_activity is not None:
                msg = """
                Calculated time bin depends on the experiment analysis. As an 
                information, we show here the analysis binning chose for each 
                animal:
                """
                for rfid in sorted(df_activity["RFID"].unique()):
                    time_window = (
                        df_activity[df_activity["RFID"] == rfid]["START_TIME"]
                        .diff()
                        .max()
                    )
                    time_window_min = round(time_window.total_seconds() / 60)
                    msg += f"<br> - {rfid}: {time_window_min} min"
                report_manager.add_card(
                    name="Time interval (bin) for each animal",
                    content=msg,
                )
            else:
                msg = """
                Time binning depends on the activity analysis, 
                which is not included in this comparison.
                """
                report_manager.add_card(
                    name="Time interval (bin) for each animal",
                    content=msg,
                )

    # ================ SETTINGS ================
    overview_type = (
        "analysis" if isinstance(settings, AnalysisSettings) else "comparison"
    )
    msg = f"""
    Here are all the settings used for this {overview_type}. They can be useful
    to keep track of the settings used for reproducible results and debugging.
    """

    report_manager.add_report(
        name="complete table",
        html_or_figure=settings.as_html(),
        top_note=msg,
    )

    # ================ TABLE ================
    report_manager.add_table_headers(name="complete table", df=df_animals)


def get_activity_card(
    df: pd.DataFrame,
    NB_ANIMALS: int,
    NB_DAYS: float,
    settings: AnalysisSettings,
):
    """Create an HTML card summarizing the average activity of each animal per
    day."""
    card = """<div style="flex: 0 0 320px; min-width: 220px;
    max-width: 400px;"> <div style="margin:0; padding:0;">
    """
    filters = []
    if settings.filter_flickering:
        filters.append("Flickering")
    if settings.filter_stop:
        filters.append("Stop")
    filters_str = ", ".join(filters) if filters else "no filters applied"
    card += f"""
    <p style='margin: 0.5em 0;'><strong>Applied filters</strong>: 
    {filters_str}
    </p>
    """

    mean_distance = round(df["DISTANCE"].sum() / NB_ANIMALS / NB_DAYS / 100)
    card += f"""
    <p style='margin: 0.5em 0;'><strong>Distance</strong>: 
    {mean_distance} <i>m</i> each day</p>
    """

    mean_speed = round(df["SPEED_MEAN"].mean())
    card += f"""
    <p style='margin: 0.5em 0;'><strong>Speed</strong>: 
    {mean_speed} <i>cm/s</i></p>
    """

    mean_duration = df["MOVE_DURATION"].sum() / NB_ANIMALS / NB_DAYS
    card += f"""
    <p style='margin: 0.5em 0;'><strong>Move</strong>: 
    {str_h_min(mean_duration)} each day
    </p>
    """

    mean_duration = df["STOP_DURATION"].sum() / NB_ANIMALS / NB_DAYS
    card += f"""
    <p style='margin: 0.5em 0;'><strong>Stop</strong>: 
    {str_h_min(mean_duration)} each day
    </p>
    """

    mean_duration = df["UNDETECTED_DURATION"].sum() / NB_ANIMALS / NB_DAYS
    card += f"""
    <p style='margin: 0.5em 0;'><strong>Undetected</strong>: 
    {str_h_min(mean_duration)} each day
    </p>
    """

    card += "</div></div>"
    return card


def get_event_card(
    df: pd.DataFrame,
    event_list: List[str],
    NB_ANIMALS: int,
    NB_DAYS: float,
):
    """Create an HTML card summarizing the average count and duration of each
    event per day, based on the provided DataFrame and list of events."""
    if NB_DAYS == 0:
        return "<p>Event card not available (need activity analysis).</p>"
    card = """<div style="flex: 0 0 320px; min-width: 220px;
    max-width: 400px;"> <div style="margin:0; padding:0;">
    """
    for event in event_list:
        logging.debug(f"Creating event card for: {event}")
        mean_count = round(
            df[df["EVENT"] == event]["EVENT_COUNT"].sum()
            / NB_ANIMALS
            / NB_DAYS
        )
        mean_duration = round(
            df[df["EVENT"] == event]["DURATION"].sum() / NB_ANIMALS / NB_DAYS
        )
        card += f"""
        <p style='margin:0;'><strong>{event}</strong></p>
        <ul style='margin:0;'>
            <li>{str_h_min(mean_duration)} each day</li>
            <li>{mean_count} event each day</li>
        </ul>
        """

    card += "</div></div>"
    return card


def get_sensors_card(df: pd.DataFrame):
    """Create an HTML card summarizing the average values of each sensor, based
    on the provided DataFrame."""
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

    card = """<div style="flex: 0 0 320px; min-width: 220px;
    max-width: 400px;"> <div style="margin:0; padding:0;">
    """
    for sensor, label, unit in zip(sensors, sensors_labels, units):
        if (
            sensor + "_MEAN" not in df.columns
            or df[sensor + "_MEAN"].isnull().all()
        ):
            card += (
                "<p style='margin: 0.5em 0;'>"
                f"{label} data not available"
                "</p>"
            )
        else:
            mean = round(df[sensor + "_MEAN"].mean(), 2)
            std = round(df[sensor + "_MEAN"].std(), 2)
            card += (
                f"<p style='margin: 0.5em 0;'>{label} : "
                f"<strong>{mean}</strong> <span>&plusmn;</span> "
                f"{std} <i>{unit}</i>"
                "</p>"
            )
    card += "</div></div>"
    return card
