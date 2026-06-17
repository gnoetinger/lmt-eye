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
