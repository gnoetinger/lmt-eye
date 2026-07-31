"""
Created on 20 dec. 2022

@author: Fab
"""

import logging

from lmtanalysis.AnimalType import AnimalType
from lmtanalysis.ParametersMouse import ParametersMouse
from lmtanalysis.ParametersRat import ParametersRat


def getAnimalTypeParameters(animalType):

    if animalType == AnimalType.MOUSE:
        return ParametersMouse()

    if animalType == AnimalType.RAT:
        return ParametersRat()

    logging.error("animal type is None")
    quit()

    return None


def get_scale_cm_over_px(animal_type: AnimalType) -> float:
    """Returns the scale in cm/px for the given animal type."""
    match animal_type:
        case AnimalType.MOUSE:
            return ParametersMouse().scaleFactor
        case AnimalType.RAT:
            return ParametersRat().scaleFactor
        case _:
            raise ValueError("Error: animal type does not exist.")


def get_arena_size_cm(animal_type: AnimalType) -> int:
    """Returns the arena size in cm for the given animal type."""
    match animal_type:
        case AnimalType.MOUSE:
            return ParametersMouse().ARENA_SIZE
        case AnimalType.RAT:
            return ParametersRat().ARENA_SIZE
        case _:
            raise ValueError("Error: animal type does not exist.")


def convert_position_to_cm(
    x: float,
    y: float,
    animal_type: AnimalType = AnimalType.MOUSE,
) -> tuple[float, float]:
    """Converts the position from px to cm for the given animal type with the
    origin at the center of the arena (from -25 to 25 cm for mouse)."""

    match animal_type:
        case AnimalType.MOUSE:
            x_origin = ParametersMouse().cornerCoordinatesOpenFieldArea[0][0]
            y_origin = ParametersMouse().cornerCoordinatesOpenFieldArea[0][1]
            cm_over_px = ParametersMouse().scaleFactor
            lmt_half_size = ParametersMouse().ARENA_SIZE / 2
        case AnimalType.RAT:
            x_origin = ParametersRat().cornerCoordinatesOpenFieldArea[0][0]
            y_origin = ParametersRat().cornerCoordinatesOpenFieldArea[0][1]
            cm_over_px = ParametersRat().scaleFactor
            lmt_half_size = ParametersRat().ARENA_SIZE / 2
        case _:
            raise ValueError("Error: animal type does not exist.")

    new_x = (x - x_origin) * cm_over_px - lmt_half_size
    new_y = (y - y_origin) * cm_over_px - lmt_half_size

    return new_x, new_y
