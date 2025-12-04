"""
Configuration file manager for OpenLISEM runfiles.

Handles parsing, modification, and writing of OpenLISEM .run configuration files.
"""

import os
from pathlib import Path
from typing import Optional, Dict, List
import copy


class ConfigManager:
    """
    Manager for OpenLISEM runfile configuration.

    OpenLISEM runfiles use a simple "name = value" format.
    This class provides methods to read, modify, and write these files.
    """

    def __init__(self, runfile_path: Optional[str] = None):
        """
        Initialize the configuration manager.

        Parameters
        ----------
        runfile_path : str, optional
            Path to the runfile to load
        """
        self._config: Dict[str, str] = {}
        self._original_order: List[str] = []
        self._base_dir = ""
        self._runfile_path = ""

        if runfile_path:
            self.load(runfile_path)

    def load(self, runfile_path: str) -> None:
        """
        Load configuration from a runfile.

        Parameters
        ----------
        runfile_path : str
            Path to the runfile
        """
        runfile_path = Path(runfile_path).resolve()
        if not runfile_path.exists():
            raise FileNotFoundError(f"Runfile not found: {runfile_path}")

        self._runfile_path = str(runfile_path)
        self._base_dir = str(runfile_path.parent)
        self._config = {}
        self._original_order = []

        with open(runfile_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith('#') or line.startswith('['):
                    continue

                # Parse "name = value"
                if '=' in line:
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        name = parts[0].strip()
                        value = parts[1].strip()

                        # Store with normalized key (lowercase)
                        key = name.lower()
                        self._config[key] = value

                        # Keep original order and casing
                        if key not in [k.lower() for k in self._original_order]:
                            self._original_order.append(name)

    def get_value(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get a configuration value.

        Parameters
        ----------
        name : str
            Parameter name
        default : str, optional
            Default value if not found

        Returns
        -------
        str or None
            Configuration value or default
        """
        key = name.lower()
        return self._config.get(key, default)

    def set_value(self, name: str, value: str) -> None:
        """
        Set a configuration value.

        Parameters
        ----------
        name : str
            Parameter name
        value : str
            New value
        """
        key = name.lower()
        self._config[key] = str(value)

        # Add to order if new
        if key not in [k.lower() for k in self._original_order]:
            self._original_order.append(name)

    def get_map_path(self, name: str) -> Optional[str]:
        """
        Get the full path to a map file.

        Parameters
        ----------
        name : str
            Map parameter name (e.g., 'dem', 'ldd', 'ksat1')

        Returns
        -------
        str or None
            Full path to the map file
        """
        # Map common names to runfile keys
        map_key_aliases = {
            "dem": ["dem", "digital elevation model"],
            "ldd": ["ldd", "local drain direction"],
            "rainfall": ["rainfall map", "rainfall station map"],
            "et": ["et map", "evapotranspiration map"],
            "cover": ["cover", "vegetation cover"],
            "lai": ["lai", "leaf area index"],
            "n": ["n", "manning's n"],
            "ksat1": ["ksat1", "saturated conductivity layer 1", "ksat"],
            "ksat2": ["ksat2", "saturated conductivity layer 2"],
            "thetai1": ["thetai1", "initial moisture content layer 1", "initial moisture content"],
            "thetai2": ["thetai2", "initial moisture content layer 2"],
            "soildepth1": ["soildepth1", "soil depth layer 1", "soil depth 1"],
            "soildepth2": ["soildepth2", "soil depth layer 2", "soil depth 2"],
            "psi1": ["psi1", "matric suction layer 1"],
            "psi2": ["psi2", "matric suction layer 2"],
            "thetas1": ["thetas1", "porosity layer 1", "porosity"],
            "cohesion": ["cohesion", "soil cohesion"],
            "aggrstab": ["aggrstab", "aggregate stability"],
            "d50": ["d50", "median grain size"],
            "d90": ["d90", "90 percentile grain size"],
            "channelwidth": ["channel width", "channelwidth"],
            "channeldepth": ["channel depth", "channeldepth"],
            "channeln": ["channel n", "channel manning"],
            "lddchannel": ["lddchannel", "channel local drain direction"],
        }

        # Normalize name
        name_lower = name.lower()

        # Get possible keys
        possible_keys = map_key_aliases.get(name_lower, [name_lower])

        # Search for value
        for key in possible_keys:
            value = self.get_value(key)
            if value:
                return self._resolve_path(value)

        return None

    def _resolve_path(self, path: str) -> str:
        """
        Resolve a path relative to the runfile directory.

        Parameters
        ----------
        path : str
            Path from configuration

        Returns
        -------
        str
            Resolved absolute path
        """
        if os.path.isabs(path):
            return path

        # Check if file exists relative to runfile
        full_path = os.path.join(self._base_dir, path)
        if os.path.exists(full_path):
            return full_path

        # Check input directory if specified
        input_dir = self.get_value("input directory")
        if input_dir:
            if not os.path.isabs(input_dir):
                input_dir = os.path.join(self._base_dir, input_dir)
            full_path = os.path.join(input_dir, path)
            if os.path.exists(full_path):
                return full_path

        # Return best guess
        return os.path.join(self._base_dir, path)

    def get_input_directory(self) -> str:
        """Get the input directory path."""
        input_dir = self.get_value("input directory") or self.get_value("input map directory")
        if input_dir:
            if os.path.isabs(input_dir):
                return input_dir
            return os.path.join(self._base_dir, input_dir)
        return self._base_dir

    def get_result_directory(self) -> str:
        """Get the result directory path."""
        result_dir = self.get_value("result directory") or self.get_value("output directory")
        if result_dir:
            if os.path.isabs(result_dir):
                return result_dir
            return os.path.join(self._base_dir, result_dir)
        return os.path.join(self._base_dir, "results")

    def write(self, output_path: Optional[str] = None) -> None:
        """
        Write configuration to a file.

        Parameters
        ----------
        output_path : str, optional
            Output path. If None, overwrites the original file.
        """
        if output_path is None:
            output_path = self._runfile_path

        # Create directory if needed
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("# OpenLISEM runfile\n")
            f.write("# Generated by BMI wrapper\n\n")

            # Write in original order
            written_keys = set()
            for name in self._original_order:
                key = name.lower()
                if key in self._config:
                    f.write(f"{name} = {self._config[key]}\n")
                    written_keys.add(key)

            # Write any new keys
            for key, value in self._config.items():
                if key not in written_keys:
                    f.write(f"{key} = {value}\n")

    def copy(self) -> "ConfigManager":
        """
        Create a copy of this configuration.

        Returns
        -------
        ConfigManager
            A deep copy of this configuration
        """
        new_config = ConfigManager()
        new_config._config = copy.deepcopy(self._config)
        new_config._original_order = copy.deepcopy(self._original_order)
        new_config._base_dir = self._base_dir
        new_config._runfile_path = self._runfile_path
        return new_config

    def get_all_parameters(self) -> Dict[str, str]:
        """
        Get all configuration parameters.

        Returns
        -------
        dict
            Dictionary of all parameters
        """
        return copy.deepcopy(self._config)

    def get_time_parameters(self) -> Dict[str, float]:
        """
        Get time-related parameters.

        Returns
        -------
        dict
            Dictionary with start_time, end_time, timestep (all in seconds)
        """
        begin_str = self.get_value("begin time") or "1:0"
        end_str = self.get_value("end time") or "1:60"
        timestep = float(self.get_value("timestep") or "60")

        event_based = self.get_value("event based") == "1"

        def parse_time(time_str: str) -> float:
            parts = time_str.split(":")
            if len(parts) == 2:
                day = int(parts[0]) - 1
                minute = int(parts[1])
                if event_based:
                    return minute * 60.0
                return (day * 1440 + minute) * 60.0
            return 0.0

        return {
            "start_time": parse_time(begin_str),
            "end_time": parse_time(end_str),
            "timestep": timestep,
            "event_based": event_based,
        }

    def get_switches(self) -> Dict[str, bool]:
        """
        Get all switch/boolean parameters.

        Returns
        -------
        dict
            Dictionary of switch values
        """
        switches = {}
        switch_names = [
            "rainfall", "event based", "include channel", "infiltration",
            "erosion", "interception", "include et", "use 2d", "include tile",
            "groundwater flow", "houses", "roads", "buffers", "culverts",
        ]

        for name in switch_names:
            value = self.get_value(name)
            switches[name] = value == "1" if value else False

        return switches

    def get_calibration_parameters(self) -> Dict[str, float]:
        """
        Get calibration parameters.

        Returns
        -------
        dict
            Dictionary of calibration values
        """
        params = {}
        cal_names = [
            "ksat calibration", "n calibration", "channel n calibration",
            "theta calibration", "psi calibration", "smax calibration",
            "rr calibration", "cohesion calibration", "aggregate stability calibration",
        ]

        for name in cal_names:
            value = self.get_value(name)
            if value:
                try:
                    params[name] = float(value)
                except ValueError:
                    params[name] = 1.0
            else:
                params[name] = 1.0

        return params
