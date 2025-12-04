"""
BMI wrapper for OpenLISEM hydrological model.

This package provides a Basic Model Interface (BMI) wrapper for the OpenLISEM
spatial surface water balance and soil erosion model.

Author: Claude (AI Assistant)
Based on OpenLISEM by Victor Jetten (v.g.jetten@utwente.nl)
License: GPLv3
"""

from .bmi_openlisem import BmiOpenLisem
from .config_manager import ConfigManager
from .map_io import MapIO

__version__ = "1.0.0"
__all__ = ["BmiOpenLisem", "ConfigManager", "MapIO"]
