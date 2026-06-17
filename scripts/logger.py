import logging
from pathlib import Path


def logger_setup(
    level: int = logging.INFO,
    display_level: bool = False,
    display_time: bool = False,
    display_file_and_line: bool = False,
    write_to_file: str | Path | None = None,
):
    """Initialize the logger with custom settings.

    Args:
        level: The logging level (e.g., logging.DEBUG, logging.INFO).
        display_time: Whether to include timestamps in log messages.
        display_file_and_line: Whether to include the source file and line
            number.
        write_to_file: Optional file path to write logs to. If None, logs go to
            console.
    """
    logging.addLevelName(logging.DEBUG, "DBUG")
    logging.addLevelName(logging.ERROR, "EROR")

    format_str = ""

    if display_time:
        format_str += "%(asctime)s "

    if display_level:
        format_str += "[%(levelname).4s] "

    format_str += "%(message)s"

    if display_file_and_line:
        format_str += " (%(filename)s, line %(lineno)d)"

    logging.basicConfig(
        filename=write_to_file,
        level=level,
        format=format_str,
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )


if __name__ == "__main__":
    logger_setup(
        level=logging.DEBUG,
        display_level=True,
        display_time=True,
        display_file_and_line=True,
        write_to_file=None,
    )
    logging.debug("This is a DEBUG message.")
    logging.info("This is an INFO message.")
    logging.warning("This is a WARNING message.")
    logging.error("This is an ERROR message.")
    logging.critical("This is a CRITICAL message.")
