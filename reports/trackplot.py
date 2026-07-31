"""
@author: xmousset
"""

import pandas as pd
import plotly.express as px

from scripts.reports_manager import HTMLReportManager
from scripts.settings import AnalysisSettings

COLOR_MAP = px.colors.qualitative.Plotly


def generic_reports(
    report_manager: HTMLReportManager,
    df: pd.DataFrame | None,
    settings: AnalysisSettings,
):
    """Analyse animal trackplot and creates a generic dataframe using the given
    `DataFrameConstructor` and construct all the generic reports into the given
    `HTMLReportManager` and returning the generated dataframe."""

    report_manager.reports_creation_focus("Trackplot")

    if df is None:
        report_manager.add_title(
            name="Analysis of animal trackplot",
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
        name=f"Analysis of animal trackplot",
        content=f"""
        This section presents the analysis of animal trackplot recorded in the
        dataset. You <b>CANNOT</b> download the underlying data used for the
        plots because the data are not binned (too much data). However, you can
        generate the complete table of trackplot data by yourself using the
        code provided in the last section of this report.""",
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

    # ================ TRACKPLOT ================

    for c in plot_parameters["category_orders"][comparator]:
        reduce_df = df[df[comparator] == c]
        fig = px.scatter(
            reduce_df,
            x="X",
            y="Y",
            color="MIN_FROM_START",
            color_continuous_scale="Plotly3",
            labels={
                "X": "X position (<i>cm</i>)",
                "Y": "Y position (<i>cm</i>)",
                "MIN_FROM_START": "Time (min)",
            },
        )
        fig.update_traces(marker=dict(opacity=0.1, size=3))
        fig.update_layout(
            margin=dict(l=0, r=0, t=30, b=0),
            xaxis=dict(scaleanchor="y", scaleratio=1),
            yaxis=dict(scaleanchor="x", scaleratio=1),
            showlegend=False,
            title=f"{comparator}: {c}",
            plot_bgcolor="rgba(0,0,0,0)",
        )

        report_title = f"Trackplot of {plot_parameters['color']}: {c}"
        report_description = f"""
        This graph shows the trackplot of each {plot_parameters['color']}.
        The color of the trackplot lines represents the time progression,
        with darker colors for the beginning (earlier time points) and
        lighter colors for the end (later time points) of the experiment.
        """

        report_manager.add_report(
            name=report_title,
            html_or_figure=fig,
            top_note=report_description,
        )

    # ================ TABLE ================
    text = (
        "The complete table data used to create the above graphs can be "
        "generated using the code below. The application use the "
        "<i>get_df_trackplot</i> method from <i>DataFrameConstructor</i> "
        "that return the trackplot data as a pandas DataFrame. Here is the code "
        "of this method (it supposed you already know how to connect to your "
        "SQLite database and how to import the necessary modules):"
    )

    code = "<pre><code class='language-python'>"
    code += """
        animal_pool = AnimalPool()
        animal_pool.loadAnimals(connection)
        animal_pool.loadDetection(lightLoad=True)
        
        # area filtering is optional,
        filter_area = False
        if filter_area:
            # Example centered area, replace with actual values
            animal_pool.filterDetectionByArea(15, 15, 35, 35)
        
        results = []
        for animal in animal_pool.getAnimalList():
        
            cm_over_px = animal.parameters.scaleFactor
            x_origin = animal.parameters.cornerCoordinatesOpenFieldArea[0][0]
            y_origin = animal.parameters.cornerCoordinatesOpenFieldArea[0][1]
            lmt_half_size = animal.parameters.ARENA_SIZE / 2
            
            xList, yList, fList = animal.get_trajectory()
            
            for i in range(len(xList)):
                if np.isnan(xList[i]).any() or np.isnan(yList[i]).any():
                    continue
                
                x_mean = np.mean(xList[i])
                y_mean = np.mean(yList[i])
                x = (x_mean - x_origin) * cm_over_px - lmt_half_size
                y = (y_mean - (-y_origin)) * cm_over_px + lmt_half_size
                results.append(
                    {
                        "RFID": animal.RFID,
                        "ANIMALID": animal.baseId,
                        "FRAME": fList[i],
                        "X": x,
                        "Y": y,
                    }
                )
        processed_df = pd.DataFrame(results)
    """
    code += "</code></pre>"

    report_manager.add_report(
        name="How to get the complete table",
        top_note=text,
        html_or_figure=code,
    )
