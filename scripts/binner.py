"""
@author: xmousset
"""

import logging

import pandas as pd
from sqlite3 import Connection
from typing import Any, Dict, List, Literal


class Binner:
    """Utility class design to manage the binning with frame numbers for LMT
    experiment.
    It cannot manage bins smaller than OneMinute.
    All bin size must be at least 1."""

    @staticmethod
    def get_last_frame(connection: Connection):
        """Get the last FRAMENUMBER and TIMESTAMP from LMT FRAME table. Useful
        to initialize the Binner with the correct time reference."""
        query = "SELECT FRAMENUMBER, TIMESTAMP FROM FRAME ORDER BY FRAMENUMBER DESC LIMIT 1"
        cursor = connection.cursor()
        cursor.execute(query)
        result = cursor.fetchone()
        cursor.close()

        if not result:
            raise ValueError("No data found in FRAME table")

        last_FRAMENUMBER = result[0]
        last_TIMESTAMP = result[1]

        if not (isinstance(last_FRAMENUMBER, int)) or not (
            isinstance(last_TIMESTAMP, int)
        ):
            raise ValueError("Invalid type of data found in FRAME table")

        return last_FRAMENUMBER, last_TIMESTAMP

    def __init__(
        self,
        db_last_frame: int,
        db_last_timestamp: int,
        bin_size: int | pd.Timedelta = 15 * 60 * 30,  # 15 minutes at 30 FPS
        bin_rounding: bool = True,
        limits: tuple[int | pd.Timestamp | None, int | pd.Timestamp | None] = (
            None,
            None,
        ),
        fps: int = 30,
        utc_offset: float = 0.0,
    ):
        """
        Initialize Binner with last FRAMENUMBER and TIMESTAMP of a
        SQLite database produce by LMT experiment.

        Args:
            db_last_frame (int): last FRAMENUMBER value in LMT FRAME table.
            db_last_timestamp (int): TIMESTAMP value of 'last_frame' (in *ms*).
            bin_size (int | pd.Timedelta | None): binning value (in *frames* or
                *timedelta*). Default to *15 min* at *30 FPS*.
            limits (tuple of int | pd.Timestamp | None, optional): starting and
                ending frame number or timestamp for binning.
                Defaults to (None, None).
            fps (int, optional): frames per second of the experiment. Defaults
                to *30*.
            utc_offset (float, optional): UTC offset in hours for correct
                timezone conversion (e.g. *+9.0* for Tokyo). Defaults to *0.0*.

        Note that the UTC offset is only used for the conversion of frame
        numbers to timestamps and vice versa, and does not affect the actual
        binning process.
        """
        self.db_last_frame = db_last_frame
        self.db_last_timestamp = db_last_timestamp
        self.utc_offset = pd.Timedelta(hours=utc_offset)
        self.limits: tuple[int, int] = (1, db_last_frame)
        self.set_parameters(
            bin_size,
            bin_rounding,
            limits[0],
            limits[1],
            utc_offset,
            fps,
        )

        logging.info(
            f"Binner initialized: "
            f"last FRAMENUMBER: {self.db_last_frame}, "
            f"last TIMESTAMP: {self.db_last_timestamp}, "
            f"experiment start: "
            f"{self.frame_to_time(1).strftime('%Y-%m-%d %H:%M:%S')}, "
            f"UTC offset: {self.utc_offset}"
        )

    def frame_to_time(self, framenumber: int) -> pd.Timestamp:
        """Convert a frame number to a pandas Timestamp."""
        time_delta = pd.to_timedelta(framenumber / self.fps, unit="s")
        return self.time_0 + time_delta

    def time_to_frame(self, time: pd.Timestamp) -> int:
        """Convert a pandas Timestamp to a frame number."""
        time_delta = time - self.time_0
        return round(time_delta.total_seconds() * self.fps)

    def timedelta_to_frames(self, delta: pd.Timedelta) -> int:
        """Convert a pandas Timedelta to number of frames."""
        return round(delta.total_seconds() * self.fps)

    def frames_to_timedelta(self, frames: int) -> pd.Timedelta:
        """Convert number of frames to a pandas Timedelta."""
        return pd.Timedelta(seconds=frames / self.fps)

    def set_parameters(
        self,
        bin_size: int | pd.Timedelta | None = None,
        bin_rounding: bool | None = None,
        start_limit: int | pd.Timestamp | None = None,
        end_limit: int | pd.Timestamp | None = None,
        utc_offset: float | None = None,
        fps: int | None = None,
    ):
        """Set bin size (in *frames*), frame limits (in *frames*), and FPS
        (*frames/second*) and save the reference bin (bin_0).
        Also initialize the reference time (time_0) that correspond to bin_0
        with appropriate timezone offset and the bin dataframe (bin_df).
        """
        # FPS
        # ----------------
        if fps is not None:
            if fps < 1:
                raise ValueError("FPS must be at least 1")
            self.fps = fps

        # UTC offset
        # ----------------
        if utc_offset is not None:
            self.utc_offset = pd.Timedelta(hours=utc_offset)

        # Time <-> Frame conversion reference
        # ----------------
        timestamp_0 = self.db_last_timestamp - (
            self.db_last_frame / self.fps * 1000
        )
        self.bin_0: Dict[str, Any] = {
            "FRAMENUMBER": 0,
            "TIMESTAMP": timestamp_0 + self.utc_offset.total_seconds() * 1000,
        }
        self.time_0 = pd.to_datetime(timestamp_0, unit="ms") + self.utc_offset

        # Bin size
        # ----------------
        if isinstance(bin_size, pd.Timedelta):
            bin_size = self.timedelta_to_frames(bin_size)

        if bin_size is not None:
            if bin_size < 1:
                raise ValueError("bin_size must be at least 1 frame")
            self.bin_size = bin_size

        # Bin rounding
        # ----------------
        if bin_rounding is not None:
            self.bin_rounding = bin_rounding

        # Start limit
        # ----------------
        if isinstance(start_limit, pd.Timestamp):
            start_limit = self.time_to_frame(start_limit)

        if start_limit is not None:
            if start_limit < 1:
                new_start = 1
            elif start_limit > self.db_last_frame:
                raise ValueError(
                    f"start_frame out of range (start_frame = {start_limit} "
                    f"> last_frame = {self.db_last_frame})"
                )
            else:
                new_start = start_limit
        else:
            new_start = self.limits[0]

        # End limit
        # ----------------
        if isinstance(end_limit, pd.Timestamp):
            end_limit = self.time_to_frame(end_limit)

        if end_limit is not None:
            if end_limit > self.db_last_frame:
                new_end = self.db_last_frame
            elif end_limit < 1:
                raise ValueError(
                    f"end_frame out of range (end_frame = {end_limit} < 1)"
                )
            else:
                new_end = end_limit
        else:
            new_end = self.limits[1]

        # Limits check
        # ----------------
        if new_start >= new_end:
            raise ValueError(
                "Invalid frame limits: start >= end "
                f"({new_start} >= {new_end})"
            )
        else:
            self.limits = (new_start, new_end)

        self.calculate_bin_df()

    def calculate_bin_df(self) -> pd.DataFrame:
        """Calculate the bin dataframe with START_FRAME, END_FRAME, START_TIME,
        and END_TIME as columns between frame 1 and last frame of database."""

        # get the starting frame number of the first bin
        if self.bin_rounding:
            # it is a negative integer if bins start at round hours
            time_1 = self.frame_to_time(self.limits[0]).floor(
                f"{self.bin_size // (self.fps)}s"
            )
            start_frame_bin_1 = self.time_to_frame(time_1)
        else:
            start_frame_bin_1 = self.limits[0]

        # calculate starting frame of each bins until last frame
        bin_start_frames: List[int] = []
        f = start_frame_bin_1
        while f < self.limits[1]:
            bin_start_frames.append(f)
            f += self.bin_size

        # create the dataframe with all bin information
        list_df = []
        for f in bin_start_frames:
            start_frame = max(1, self.limits[0], f)
            end_frame = min(
                self.db_last_frame, self.limits[1], f + self.bin_size - 1
            )
            list_df.append(
                {
                    "START_FRAME": start_frame,
                    "END_FRAME": end_frame,
                    "START_TIME": self.frame_to_time(start_frame),
                    "END_TIME": self.frame_to_time(end_frame),
                }
            )

        self.bin_df = pd.DataFrame(
            list_df,
            columns=["START_FRAME", "END_FRAME", "START_TIME", "END_TIME"],
        )
        return self.bin_df

    def get_bin_list(
        self,
        bin_edge: Literal["START", "END"],
        unit: Literal["FRAME", "TIME"] = "FRAME",
    ) -> list[Any]:
        """
        Get a list of bin edges (frame numbers or timestamps) between limits.

        Parameters
        ----------
        bin_edge : {'START', 'END'}
            Whether to return the start or end of each bin.
        unit : {'FRAME', 'TIME'}, optional
            Whether to return frame numbers ('FRAME') or timestamps ('TIME').
            Default is 'FRAME'.

        Returns
        -------
        list of int or list of pandas.Timestamp
            List of bin edges (either frame numbers or timestamps) within the
            specified range.
        """
        return self.bin_df[f"{bin_edge}_{unit}"].tolist()

    def get_bin_iterator(self):
        """Get a bin iterator (list of (start, end) tuples) between
        'self.limits'.
        """

        frames_start = self.get_bin_list("START")
        frames_end = self.get_bin_list("END")

        bin_iterator: List[tuple[int, int]] = []
        for start, end in zip(frames_start, frames_end):
            bin_iterator.append((start, end))
            
        logging.debug(
            f"Bin iterator: {len(bin_iterator)} bins "
            f"between frames {self.limits[0]} and {self.limits[1]}."
        )

        return bin_iterator

    def split_iterator_in_chunks(
        self,
        chunk_size: int | pd.Timedelta,
        bin_iterator: List[tuple[int, int]],
    ):
        """Split the given bin iterator (list of (start, end) tuples), in
        chunks of chunk_size (in *frames* or *timedelta*). Useful to split the
        processing of bins in smaller chunks for memory usage reduction.
        """

        if isinstance(chunk_size, pd.Timedelta):
            chunk_size = self.timedelta_to_frames(chunk_size)

        chunked_iterator: List[List[tuple[int, int]]] = [
            [bin_iterator[0]],
        ]
        chunk_start = bin_iterator[0][0]

        for bin in bin_iterator[1:]:
            if bin[1] - chunk_start + 1 < chunk_size:
                chunked_iterator[-1].append(bin)
            else:
                chunked_iterator.append([bin])
                chunk_start = bin[0]

        logging.debug(
            f"Bin iterator split in {len(chunked_iterator)} chunks "
            f"of size {chunk_size} frames."
        )
        logging.debug(
            f"Chunks: {[
                (chunk[0][0], chunk[-1][1])
                for chunk in chunked_iterator
            ]}"
        )

        return chunked_iterator
