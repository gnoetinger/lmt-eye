"""
@creation: 26-01-2026
@last update: 04-06-2026
@author: xmousset
"""

import logging
import importlib.util
from pathlib import Path
from types import ModuleType

from events.official import (
    BuildEventApproachContact,
    BuildEventApproachRear,
    BuildEventCenterPeripheryLocation,
    BuildEventDetection,
    BuildEventFlickering,
    BuildEventFollowZone,
    BuildEventGetAway,
    BuildEventGroup2,
    BuildEventGroup3,
    BuildEventGroup3MakeBreak,
    BuildEventGroup4,
    BuildEventGroup4MakeBreak,
    BuildEventLongChase,
    BuildEventMove,
    BuildEventMoveSpeedCategories,
    BuildEventNest3,
    BuildEventNest4,
    BuildEventOralGenitalContact,
    BuildEventOralOralContact,
    BuildEventOralSideSequence,
    BuildEventRear5,
    BuildEventRearCenterPeriphery,
    BuildEventSAP,
    BuildEventSideBySide,
    BuildEventSideBySideOpposite,
    BuildEventSocialApproach,
    BuildEventSocialEscape,
    BuildEventStop,
    BuildEventTrain2,
    BuildEventTrain3,
    BuildEventTrain4,
    BuildEventWallJump,
)

OFFICIAL_EVENTS: dict[str, ModuleType | str | None] = {
    "Approach": None,
    "Contact": None,
    "Behind": None,
    "Break contact": None,
    "Escape": None,
    "Follow": None,
    "Head detected": None,
    "Look down": None,
    "RFID MATCH": None,
    "RFID MISMATCH": None,
    "Detection": BuildEventDetection,
    "Oral-oral Contact": BuildEventOralOralContact,
    "Oral-genital Contact": BuildEventOralGenitalContact,
    "Side by side Contact": BuildEventSideBySide,
    "Side by side Contact, opposite way": BuildEventSideBySideOpposite,
    "Train2": BuildEventTrain2,
    "Train3": BuildEventTrain3,
    "Train4": BuildEventTrain4,
    "Move": BuildEventMove,
    "Move isolated": "Move",
    "Move in contact": "Move",
    "FollowZone": BuildEventFollowZone,
    "Rearing": BuildEventRear5,
    "Rear in contact": "Rearing",
    "Rear isolated": "Rearing",
    "Center Zone": BuildEventCenterPeripheryLocation,
    "Periphery Zone": "Center Zone",
    "Rear at periphery": BuildEventRearCenterPeriphery,
    "Rear in centerWindow": "Rear at periphery",
    "Social approach": BuildEventSocialApproach,
    "Get away": BuildEventGetAway,
    "Social escape": BuildEventSocialEscape,
    "Approach rear": BuildEventApproachRear,
    "Group2": BuildEventGroup2,
    "Group3": BuildEventGroup3,
    "Group4": BuildEventGroup4,
    "Group 3 break": BuildEventGroup3MakeBreak,
    "Group 4 break": BuildEventGroup4MakeBreak,
    "Group 3 make": "Group 3 break",
    "Group 4 make": "Group 4 break",
    "Stop": BuildEventStop,
    "Stop in contact": "Stop",
    "Stop isolated": "Stop",
    "Approach contact": BuildEventApproachContact,
    "seq oral oral - oral genital": BuildEventOralSideSequence,
    "Nest3_": BuildEventNest3,
    "Nest4_": BuildEventNest4,
    "Move high speed": BuildEventMoveSpeedCategories,
    "longChase": BuildEventLongChase,
    "SAP": BuildEventSAP,
    "WallJump": BuildEventWallJump,
    "Flickering": BuildEventFlickering,
}


def _load_custom_events() -> dict[str, ModuleType]:
    """
    Load all custom event modules from events/custom directory.
    (Similar to OFFICIAL_EVENTS but for custom events)

    Returns
    -------
    dict[str, ModuleType]
        Dictionary with event name as key (get from EVENTS_NAME) and module as
        value.
        Example: {"Speed": <module>, "Rearing": <module>, ...}
    """
    logging.info("Loading custom events...")
    custom_events_dir = Path(__file__).parent / "custom"
    events_dict: dict[str, ModuleType] = {}

    if not custom_events_dir.exists():
        logging.warning(f"{custom_events_dir} does not exist.")
        return events_dict

    # Iterate through all .py files in events/custom
    for file_path in custom_events_dir.glob("BuildEvent*.py"):

        try:
            # Load module dynamically
            spec = importlib.util.spec_from_file_location(
                file_path.stem,
                file_path,
            )
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Get EVENTS_NAME from module and add to dict
            if hasattr(module, "EVENTS_NAME"):
                for event_name in module.EVENTS_NAME:
                    events_dict[event_name] = module
                    logging.info(f"✓ {event_name}")
            else:
                logging.warning(
                    f"⚠ {file_path.name} has no EVENTS_NAME attribute"
                )

        except Exception as e:
            logging.error(f"✗ Loading error: {file_path.name}\nException: {e}")

    logging.info(
        f"Finished loading custom events. Total loaded: {len(events_dict)}"
    )
    return events_dict


# Load custom events once at module import time
CUSTOM_EVENTS: dict[str, ModuleType] = _load_custom_events()


def sort_in_official_order(
    event_names: list[ModuleType] | set[ModuleType],
) -> list[ModuleType]:
    """Sort a list of event names based on the order defined in OFFICIAL_EVENTS."""

    if isinstance(event_names, set):
        event_names = list(event_names)

    official_order = list(OFFICIAL_EVENTS.keys())
    sorted_events = sorted(
        event_names,
        key=lambda name: (
            official_order.index(name)
            if name in official_order
            else float("inf")
        ),
    )
    return sorted_events


def get_official_events_name() -> set[str]:
    """Return a set of official event names."""
    return set(OFFICIAL_EVENTS.keys())


def get_custom_events_name() -> set[str]:
    """Return a set of custom event names."""
    return set(CUSTOM_EVENTS.keys())


def get_modules_from_events_name(names: list[str] | set[str]):
    """Get a set of unique modules associated with a list of event names."""
    modules: set[ModuleType] = set()

    if isinstance(names, list):
        names = set(names)

    official_events = get_official_events_name()
    custom_events = get_custom_events_name()

    for event_name in names:
        module = None

        if event_name in official_events:
            module = OFFICIAL_EVENTS.get(event_name, None)
            if isinstance(module, str):
                module = OFFICIAL_EVENTS.get(module, None)

        elif event_name in custom_events:
            module = CUSTOM_EVENTS.get(event_name, None)

        if isinstance(module, ModuleType):
            modules.add(module)

    return modules
