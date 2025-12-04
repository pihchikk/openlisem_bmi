"""
BMI wrapper for OpenLISEM hydrological model.

Implements the CSDMS Basic Model Interface (BMI) 2.0 specification.
https://bmi.readthedocs.io/
"""

import os
import subprocess
import tempfile
import shutil
import numpy as np
from typing import Tuple, List, Optional
from pathlib import Path

from .config_manager import ConfigManager
from .map_io import MapIO


class BmiOpenLisem:
    """
    Basic Model Interface (BMI) wrapper for OpenLISEM.

    OpenLISEM is a spatial surface water balance and soil erosion model.
    This wrapper allows coupling with other BMI-compliant models.

    Example usage:
        >>> model = BmiOpenLisem()
        >>> model.initialize("path/to/runfile.run")
        >>> while model.get_current_time() < model.get_end_time():
        ...     model.update()
        >>> model.finalize()
    """

    _name = "OpenLISEM"
    _time_units = "s"  # seconds

    # Input variables that can be set during runtime
    _input_var_names = [
        "rainfall_rate",           # Rain intensity [m/s]
        "potential_evapotranspiration",  # ET rate [m/s]
        "water_surface__height",   # Surface water height WH [m]
        "soil_water__initial_content",  # Initial soil moisture [-]
        "land_surface__elevation", # DEM [m]
    ]

    # Output variables that can be retrieved
    _output_var_names = [
        "water_surface__height",   # Surface water height WH [m]
        "water_surface__discharge", # Discharge Q [m3/s]
        "water_surface__velocity", # Flow velocity V [m/s]
        "soil_water__infiltration_volume", # Infiltration volume [m3]
        "soil_water__content",     # Soil moisture content [-]
        "sediment__concentration", # Sediment concentration [kg/m3]
        "sediment__mass_flux",     # Sediment flux [kg/s]
        "channel_water__height",   # Channel water height [m]
        "channel_water__discharge", # Channel discharge [m3/s]
    ]

    # Map variable names to OpenLISEM internal names
    _var_name_map = {
        "rainfall_rate": "Rain",
        "potential_evapotranspiration": "ETp",
        "water_surface__height": "WH",
        "water_surface__discharge": "Qoutput",
        "water_surface__velocity": "V",
        "soil_water__infiltration_volume": "InfilVol",
        "soil_water__content": "ThetaI1",
        "soil_water__initial_content": "ThetaI1",
        "sediment__concentration": "Conc",
        "sediment__mass_flux": "Qsoutput",
        "channel_water__height": "ChannelWH",
        "channel_water__discharge": "ChannelQ",
        "land_surface__elevation": "DEM",
    }

    # Variable units following CSDMS standard names
    _var_units = {
        "rainfall_rate": "m/s",
        "potential_evapotranspiration": "m/s",
        "water_surface__height": "m",
        "water_surface__discharge": "m3/s",
        "water_surface__velocity": "m/s",
        "soil_water__infiltration_volume": "m3",
        "soil_water__content": "-",
        "soil_water__initial_content": "-",
        "sediment__concentration": "kg/m3",
        "sediment__mass_flux": "kg/s",
        "channel_water__height": "m",
        "channel_water__discharge": "m3/s",
        "land_surface__elevation": "m",
    }

    def __init__(self):
        """Initialize the BMI wrapper (not the model)."""
        self._initialized = False
        self._config = None
        self._config_file = None
        self._working_dir = None
        self._temp_dir = None
        self._current_time = 0.0
        self._start_time = 0.0
        self._end_time = 0.0
        self._time_step = 0.0
        self._grid_shape = (0, 0)
        self._grid_spacing = (0.0, 0.0)
        self._grid_origin = (0.0, 0.0)
        self._lisem_executable = None
        self._map_io = None
        self._state_maps = {}  # Cache for current state maps

    def initialize(self, config_file: str) -> None:
        """
        Initialize the model from a configuration file.

        Parameters
        ----------
        config_file : str
            Path to the OpenLISEM runfile (.run file)
        """
        if self._initialized:
            raise RuntimeError("Model already initialized. Call finalize() first.")

        config_file = Path(config_file).resolve()
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")

        self._config_file = str(config_file)
        self._working_dir = str(config_file.parent)

        # Create temporary directory for intermediate files
        self._temp_dir = tempfile.mkdtemp(prefix="openlisem_bmi_")

        # Load and parse configuration
        self._config = ConfigManager(self._config_file)

        # Find OpenLISEM executable
        self._lisem_executable = self._find_executable()

        # Initialize map I/O handler
        self._map_io = MapIO(self._working_dir)

        # Extract time parameters
        self._parse_time_parameters()

        # Extract grid parameters from DEM
        self._parse_grid_parameters()

        # Set current time to start time
        self._current_time = self._start_time

        self._initialized = True

    def _find_executable(self) -> str:
        """Find the OpenLISEM executable."""
        # Check common locations
        search_paths = [
            Path(__file__).parent.parent.parent / "build" / "Lisem",  # Local build
            Path(__file__).parent.parent.parent / "Lisem",  # Local
            Path("/usr/local/bin/Lisem"),
            Path("/usr/bin/Lisem"),
            Path.home() / "bin" / "Lisem",
        ]

        # Also check environment variable
        env_path = os.environ.get("OPENLISEM_EXECUTABLE")
        if env_path:
            search_paths.insert(0, Path(env_path))

        for path in search_paths:
            if path.exists() and os.access(path, os.X_OK):
                return str(path)

        # Try to find in PATH
        result = shutil.which("Lisem")
        if result:
            return result

        raise FileNotFoundError(
            "OpenLISEM executable not found. Set OPENLISEM_EXECUTABLE environment "
            "variable or ensure 'Lisem' is in your PATH."
        )

    def _parse_time_parameters(self) -> None:
        """Parse time parameters from configuration."""
        begin_time_str = self._config.get_value("Begin Time")
        end_time_str = self._config.get_value("End Time")
        timestep = float(self._config.get_value("Timestep"))

        # Parse time format "day:minute"
        self._start_time = self._parse_time_string(begin_time_str)
        self._end_time = self._parse_time_string(end_time_str)
        self._time_step = timestep  # Already in seconds

    def _parse_time_string(self, time_str: str) -> float:
        """Parse time string 'day:minute' to seconds."""
        parts = time_str.split(":")
        if len(parts) == 2:
            day = int(parts[0]) - 1  # Day 1 is actually day 0
            minute = int(parts[1])
            # Check if event-based (ignore day)
            event_based = self._config.get_value("Event based") == "1"
            if event_based:
                return minute * 60.0  # Convert minutes to seconds
            else:
                return (day * 1440 + minute) * 60.0  # Full day calculation
        return 0.0

    def _parse_grid_parameters(self) -> None:
        """Parse grid parameters from DEM map."""
        dem_file = self._config.get_map_path("dem")
        if dem_file and Path(dem_file).exists():
            dem_data, metadata = self._map_io.read_map(dem_file)
            self._grid_shape = dem_data.shape
            self._grid_spacing = (metadata.get("cellsize", 1.0),
                                  metadata.get("cellsize", 1.0))
            self._grid_origin = (metadata.get("xllcorner", 0.0),
                                metadata.get("yllcorner", 0.0))
        else:
            raise FileNotFoundError(f"DEM file not found: {dem_file}")

    def update(self) -> None:
        """Advance the model by one time step."""
        if not self._initialized:
            raise RuntimeError("Model not initialized. Call initialize() first.")

        if self._current_time >= self._end_time:
            return

        # Calculate next time
        next_time = min(self._current_time + self._time_step, self._end_time)

        # Run model for this time step
        self._run_timestep(self._current_time, next_time)

        # Update current time
        self._current_time = next_time

    def update_until(self, time: float) -> None:
        """
        Advance the model until a specified time.

        Parameters
        ----------
        time : float
            Target time in seconds
        """
        if not self._initialized:
            raise RuntimeError("Model not initialized. Call initialize() first.")

        while self._current_time < time and self._current_time < self._end_time:
            self.update()

    def update_frac(self, frac: float) -> None:
        """
        Advance the model by a fraction of a time step.

        Parameters
        ----------
        frac : float
            Fraction of time step (0-1)
        """
        if not self._initialized:
            raise RuntimeError("Model not initialized. Call initialize() first.")

        # For OpenLISEM, we can only do full timesteps
        # This is a limitation of the subprocess approach
        if frac >= 1.0:
            self.update()

    def _run_timestep(self, start_time: float, end_time: float) -> None:
        """Run the model for a single time step."""
        # Create temporary runfile with adjusted times
        temp_runfile = self._create_temp_runfile(start_time, end_time)

        # Run OpenLISEM
        cmd = [
            self._lisem_executable,
            "-ni",  # No interface (batch mode)
            "-f",   # Force result directory creation
            "-r", temp_runfile
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=self._working_dir,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"OpenLISEM execution failed:\n{result.stderr}\n{result.stdout}"
                )

        except subprocess.TimeoutExpired:
            raise RuntimeError("OpenLISEM execution timed out after 1 hour")

        # Load output maps into state cache
        self._load_state_maps()

    def _create_temp_runfile(self, start_time: float, end_time: float) -> str:
        """Create a temporary runfile with adjusted time parameters."""
        temp_runfile = os.path.join(self._temp_dir, "temp_run.run")

        # Convert seconds back to day:minute format
        start_str = self._time_to_string(start_time)
        end_str = self._time_to_string(end_time)

        # Create modified config
        modified_config = self._config.copy()
        modified_config.set_value("Begin Time", start_str)
        modified_config.set_value("End Time", end_str)

        # Set output directory to temp
        result_dir = os.path.join(self._temp_dir, "results")
        os.makedirs(result_dir, exist_ok=True)
        modified_config.set_value("Result Directory", result_dir)

        # Write temporary runfile
        modified_config.write(temp_runfile)

        return temp_runfile

    def _time_to_string(self, time_seconds: float) -> str:
        """Convert time in seconds to 'day:minute' format."""
        event_based = self._config.get_value("Event based") == "1"

        if event_based:
            minutes = int(time_seconds / 60)
            return f"1:{minutes}"
        else:
            total_minutes = int(time_seconds / 60)
            days = total_minutes // 1440 + 1  # Day 1 is first day
            minutes = total_minutes % 1440
            return f"{days}:{minutes}"

    def _load_state_maps(self) -> None:
        """Load current state maps from output directory."""
        result_dir = os.path.join(self._temp_dir, "results")

        # Map of output variable names to possible file patterns
        map_patterns = {
            "WH": ["runoff*.map", "wh*.map"],
            "V": ["vel*.map", "v*.map"],
            "Qoutput": ["q*.map", "discharge*.map"],
            "InfilVol": ["inf*.map", "infiltration*.map"],
            "Conc": ["conc*.map"],
            "Qsoutput": ["qs*.map", "sediment*.map"],
            "ChannelWH": ["chanwh*.map"],
            "ChannelQ": ["chanq*.map"],
        }

        # Try to load maps from results
        for var_name, patterns in map_patterns.items():
            for pattern in patterns:
                import glob
                files = glob.glob(os.path.join(result_dir, pattern))
                if files:
                    # Get the latest file
                    latest_file = max(files, key=os.path.getctime)
                    try:
                        data, _ = self._map_io.read_map(latest_file)
                        self._state_maps[var_name] = data
                        break
                    except Exception:
                        continue

    def finalize(self) -> None:
        """Clean up the model."""
        if self._temp_dir and os.path.exists(self._temp_dir):
            shutil.rmtree(self._temp_dir, ignore_errors=True)

        self._initialized = False
        self._config = None
        self._state_maps = {}

    # BMI Info Functions

    def get_component_name(self) -> str:
        """Get the name of the model component."""
        return self._name

    def get_input_item_count(self) -> int:
        """Get the number of input variables."""
        return len(self._input_var_names)

    def get_output_item_count(self) -> int:
        """Get the number of output variables."""
        return len(self._output_var_names)

    def get_input_var_names(self) -> Tuple[str, ...]:
        """Get names of input variables."""
        return tuple(self._input_var_names)

    def get_output_var_names(self) -> Tuple[str, ...]:
        """Get names of output variables."""
        return tuple(self._output_var_names)

    # BMI Variable Info Functions

    def get_var_grid(self, name: str) -> int:
        """Get the grid identifier for a variable."""
        self._check_var_name(name)
        return 0  # All variables use the same grid

    def get_var_type(self, name: str) -> str:
        """Get the data type of a variable."""
        self._check_var_name(name)
        return "float64"

    def get_var_units(self, name: str) -> str:
        """Get the units of a variable."""
        self._check_var_name(name)
        return self._var_units.get(name, "-")

    def get_var_itemsize(self, name: str) -> int:
        """Get the size (in bytes) of a single element of a variable."""
        self._check_var_name(name)
        return 8  # float64

    def get_var_nbytes(self, name: str) -> int:
        """Get the total size (in bytes) of a variable."""
        self._check_var_name(name)
        return self._grid_shape[0] * self._grid_shape[1] * 8

    def get_var_location(self, name: str) -> str:
        """Get the grid element type for a variable."""
        self._check_var_name(name)
        return "node"  # Cell-centered values

    def _check_var_name(self, name: str) -> None:
        """Check if a variable name is valid."""
        all_vars = set(self._input_var_names) | set(self._output_var_names)
        if name not in all_vars:
            raise ValueError(f"Unknown variable: {name}")

    # BMI Time Functions

    def get_current_time(self) -> float:
        """Get the current model time."""
        return self._current_time

    def get_start_time(self) -> float:
        """Get the model start time."""
        return self._start_time

    def get_end_time(self) -> float:
        """Get the model end time."""
        return self._end_time

    def get_time_units(self) -> str:
        """Get the time units."""
        return self._time_units

    def get_time_step(self) -> float:
        """Get the model time step."""
        return self._time_step

    # BMI Grid Functions

    def get_grid_rank(self, grid: int) -> int:
        """Get the number of dimensions of a grid."""
        return 2  # 2D grid

    def get_grid_size(self, grid: int) -> int:
        """Get the total number of elements in a grid."""
        return self._grid_shape[0] * self._grid_shape[1]

    def get_grid_type(self, grid: int) -> str:
        """Get the type of a grid."""
        return "uniform_rectilinear"

    def get_grid_shape(self, grid: int, shape: np.ndarray) -> np.ndarray:
        """Get the shape of a grid."""
        shape[0] = self._grid_shape[0]
        shape[1] = self._grid_shape[1]
        return shape

    def get_grid_spacing(self, grid: int, spacing: np.ndarray) -> np.ndarray:
        """Get the spacing between grid nodes."""
        spacing[0] = self._grid_spacing[0]
        spacing[1] = self._grid_spacing[1]
        return spacing

    def get_grid_origin(self, grid: int, origin: np.ndarray) -> np.ndarray:
        """Get the origin of a grid."""
        origin[0] = self._grid_origin[0]
        origin[1] = self._grid_origin[1]
        return origin

    def get_grid_x(self, grid: int, x: np.ndarray) -> np.ndarray:
        """Get the x-coordinates of grid nodes."""
        for i in range(self._grid_shape[1]):
            x[i] = self._grid_origin[0] + i * self._grid_spacing[0]
        return x

    def get_grid_y(self, grid: int, y: np.ndarray) -> np.ndarray:
        """Get the y-coordinates of grid nodes."""
        for i in range(self._grid_shape[0]):
            y[i] = self._grid_origin[1] + i * self._grid_spacing[1]
        return y

    def get_grid_z(self, grid: int, z: np.ndarray) -> np.ndarray:
        """Get the z-coordinates of grid nodes (not applicable for 2D)."""
        return z

    def get_grid_node_count(self, grid: int) -> int:
        """Get the number of nodes in a grid."""
        return self.get_grid_size(grid)

    def get_grid_edge_count(self, grid: int) -> int:
        """Get the number of edges in a grid."""
        # For structured grid: (rows-1)*cols + rows*(cols-1)
        rows, cols = self._grid_shape
        return (rows - 1) * cols + rows * (cols - 1)

    def get_grid_face_count(self, grid: int) -> int:
        """Get the number of faces in a grid."""
        rows, cols = self._grid_shape
        return (rows - 1) * (cols - 1)

    # BMI Getter Functions

    def get_value(self, name: str, dest: np.ndarray) -> np.ndarray:
        """
        Get a copy of a variable's values.

        Parameters
        ----------
        name : str
            Variable name
        dest : np.ndarray
            Destination array to copy values into

        Returns
        -------
        np.ndarray
            Array with variable values
        """
        self._check_var_name(name)

        internal_name = self._var_name_map.get(name, name)

        if internal_name in self._state_maps:
            # Use cached state
            src = self._state_maps[internal_name]
        else:
            # Try to load from input directory
            src = self._load_input_map(name)

        if src is not None:
            dest[:] = src.flatten()
        else:
            dest[:] = 0.0

        return dest

    def get_value_ptr(self, name: str) -> np.ndarray:
        """
        Get a reference to a variable's values.

        Note: For this file-based wrapper, this returns a copy, not a reference.
        """
        self._check_var_name(name)

        internal_name = self._var_name_map.get(name, name)

        if internal_name in self._state_maps:
            return self._state_maps[internal_name].flatten()
        else:
            src = self._load_input_map(name)
            if src is not None:
                return src.flatten()
            return np.zeros(self.get_grid_size(0))

    def get_value_at_indices(self, name: str, dest: np.ndarray,
                             inds: np.ndarray) -> np.ndarray:
        """Get variable values at specific indices."""
        self._check_var_name(name)

        full_values = self.get_value_ptr(name)
        dest[:] = full_values[inds]
        return dest

    def _load_input_map(self, var_name: str) -> Optional[np.ndarray]:
        """Load an input map by variable name."""
        internal_name = self._var_name_map.get(var_name, var_name)

        # Map to runfile keys
        runfile_keys = {
            "DEM": "dem",
            "Rain": "rainfall",
            "ETp": "et",
            "ThetaI1": "thetai1",
            "WH": "wh",
        }

        key = runfile_keys.get(internal_name, internal_name.lower())
        map_path = self._config.get_map_path(key)

        if map_path and Path(map_path).exists():
            data, _ = self._map_io.read_map(map_path)
            return data

        return None

    # BMI Setter Functions

    def set_value(self, name: str, src: np.ndarray) -> None:
        """
        Set the values of a variable.

        Parameters
        ----------
        name : str
            Variable name
        src : np.ndarray
            Array with new values
        """
        if name not in self._input_var_names:
            raise ValueError(f"Cannot set output variable: {name}")

        internal_name = self._var_name_map.get(name, name)

        # Reshape if needed
        data = src.reshape(self._grid_shape)

        # Store in state
        self._state_maps[internal_name] = data

        # Write to file for next timestep
        self._write_input_map(name, data)

    def set_value_at_indices(self, name: str, inds: np.ndarray,
                             src: np.ndarray) -> None:
        """Set variable values at specific indices."""
        if name not in self._input_var_names:
            raise ValueError(f"Cannot set output variable: {name}")

        # Get current values
        current = self.get_value_ptr(name).copy()
        current[inds] = src

        # Set full array
        self.set_value(name, current)

    def _write_input_map(self, var_name: str, data: np.ndarray) -> None:
        """Write input map for use in next timestep."""
        internal_name = self._var_name_map.get(var_name, var_name)

        # Determine output path
        map_file = os.path.join(self._temp_dir, f"{internal_name}_input.map")

        # Get reference metadata from DEM
        dem_path = self._config.get_map_path("dem")
        if dem_path:
            _, metadata = self._map_io.read_map(dem_path)
        else:
            metadata = {
                "cellsize": self._grid_spacing[0],
                "xllcorner": self._grid_origin[0],
                "yllcorner": self._grid_origin[1],
            }

        # Write map
        self._map_io.write_map(map_file, data, metadata)

        # Update config to use this map
        runfile_keys = {
            "Rain": "Rainfall map",
            "ETp": "ET map",
            "ThetaI1": "Initial Moisture content",
            "WH": "Initial water level",
            "DEM": "dem",
        }

        key = runfile_keys.get(internal_name)
        if key and self._config:
            self._config.set_value(key, map_file)
