"""
BMI wrapper for OpenLISEM hydrological model.

This is a standalone Python BMI implementation that can run basic
hydrological simulations without requiring the compiled OpenLISEM executable.
Implements the CSDMS Basic Model Interface (BMI) 2.0 specification.
"""

import numpy as np
from typing import Tuple, Optional
from pathlib import Path

from .config_manager import ConfigManager
from .map_io import MapIO


class BmiOpenLisem:
    """
    BMI wrapper for OpenLISEM - Standalone Python Implementation.

    This wrapper provides a simplified hydrological model that can be used
    for model coupling experiments without requiring the compiled OpenLISEM.

    Features:
    - Rainfall-runoff simulation
    - Simple infiltration (Green-Ampt)
    - Overland flow routing
    - Evapotranspiration

    Example:
        >>> model = BmiOpenLisem()
        >>> model.initialize("path/to/runfile.run")
        >>> while model.get_current_time() < model.get_end_time():
        ...     model.update()
        >>> model.finalize()
    """

    _name = "OpenLISEM-Python"
    _time_units = "s"

    # Input variables
    _input_var_names = [
        "rainfall_rate",
        "potential_evapotranspiration",
        "water_surface__height",
        "soil_water__content",
        "land_surface__elevation",
    ]

    # Output variables
    _output_var_names = [
        "water_surface__height",
        "water_surface__discharge",
        "water_surface__velocity",
        "soil_water__infiltration_rate",
        "soil_water__cumulative_infiltration",
        "soil_water__content",
        "surface_water__runoff_volume",
        "channel_water__discharge",
    ]

    # Variable units
    _var_units = {
        "rainfall_rate": "m/s",
        "potential_evapotranspiration": "m/s",
        "water_surface__height": "m",
        "water_surface__discharge": "m3/s",
        "water_surface__velocity": "m/s",
        "soil_water__infiltration_rate": "m/s",
        "soil_water__cumulative_infiltration": "m",
        "soil_water__content": "-",
        "surface_water__runoff_volume": "m3",
        "land_surface__elevation": "m",
        "channel_water__discharge": "m3/s",
    }

    def __init__(self):
        """Initialize the BMI wrapper."""
        self._initialized = False
        self._config = None
        self._config_file = None
        self._working_dir = None

        # Time parameters
        self._current_time = 0.0
        self._start_time = 0.0
        self._end_time = 3600.0
        self._time_step = 60.0

        # Grid parameters
        self._nrows = 0
        self._ncols = 0
        self._cellsize = 10.0
        self._grid_origin = (0.0, 0.0)

        # State variables
        self._dem = None
        self._ldd = None
        self._wh = None
        self._v = None
        self._q = None
        self._infil_cum = None
        self._infil_rate = None
        self._theta = None
        self._runoff_vol = None
        self._rain = None
        self._etp = None

        # Soil parameters
        self._ksat = None
        self._psi = None
        self._porosity = None
        self._theta_init = None
        self._manning_n = None
        self._slope = None

        self._map_io = None

    def initialize(self, config_file: str = "") -> None:
        """
        Initialize the model.

        Parameters
        ----------
        config_file : str
            Path to OpenLISEM runfile (.run) or empty for default test grid
        """
        if self._initialized:
            raise RuntimeError("Model already initialized. Call finalize() first.")

        config_path = Path(config_file) if config_file else None

        if config_path and config_path.exists():
            self._config_file = str(config_path.resolve())
            self._working_dir = str(config_path.parent)
            self._config = ConfigManager(self._config_file)
            self._map_io = MapIO(self._working_dir)
            self._load_from_config()
        else:
            self._create_default_config()

        self._current_time = self._start_time
        self._initialized = True

        print(f"Initialized {self._name}")
        print(f"  Grid: {self._nrows} x {self._ncols}, cellsize: {self._cellsize} m")
        print(f"  Time: {self._start_time} to {self._end_time} s, dt={self._time_step} s")

    def _load_from_config(self) -> None:
        """Load model configuration from runfile."""
        time_params = self._config.get_time_parameters()
        self._start_time = time_params["start_time"]
        self._end_time = time_params["end_time"]
        self._time_step = time_params["timestep"]

        dem_path = self._config.get_map_path("dem")
        if dem_path and Path(dem_path).exists():
            self._dem, meta = self._map_io.read_map(dem_path)
            self._nrows, self._ncols = self._dem.shape
            self._cellsize = meta.get("cellsize", 10.0)
            self._grid_origin = (meta.get("xllcorner", 0.0),
                                meta.get("yllcorner", 0.0))
        else:
            self._nrows, self._ncols = 100, 100
            self._dem = np.zeros((self._nrows, self._ncols))

        self._initialize_arrays()
        self._load_optional_maps()

    def _create_default_config(self) -> None:
        """Create default test configuration."""
        self._nrows, self._ncols = 50, 50
        self._cellsize = 10.0
        self._grid_origin = (0.0, 0.0)
        self._start_time = 0.0
        self._end_time = 3600.0
        self._time_step = 60.0

        # Sloped DEM
        y = np.arange(self._nrows) * self._cellsize
        Y = np.tile(y.reshape(-1, 1), (1, self._ncols))
        self._dem = 100.0 - 0.01 * Y

        self._initialize_arrays()

    def _initialize_arrays(self) -> None:
        """Initialize all state arrays."""
        shape = (self._nrows, self._ncols)

        self._wh = np.zeros(shape)
        self._v = np.zeros(shape)
        self._q = np.zeros(shape)
        self._infil_cum = np.zeros(shape)
        self._infil_rate = np.zeros(shape)
        self._runoff_vol = np.zeros(shape)
        self._rain = np.zeros(shape)
        self._etp = np.zeros(shape)

        self._ksat = np.full(shape, 1e-5)
        self._psi = np.full(shape, 0.1)
        self._porosity = np.full(shape, 0.4)
        self._theta_init = np.full(shape, 0.2)
        self._theta = self._theta_init.copy()
        self._manning_n = np.full(shape, 0.03)

        self._calculate_slope()
        self._create_simple_ldd()

    def _load_optional_maps(self) -> None:
        """Load optional input maps."""
        if not self._config:
            return

        map_loaders = {
            "ksat1": ("_ksat", 1e-5),
            "n": ("_manning_n", 0.03),
            "thetai1": ("_theta_init", 0.2),
            "psi1": ("_psi", 0.1),
            "thetas1": ("_porosity", 0.4),
        }

        for config_key, (attr, default) in map_loaders.items():
            map_path = self._config.get_map_path(config_key)
            if map_path and Path(map_path).exists():
                try:
                    data, _ = self._map_io.read_map(map_path)
                    setattr(self, attr, data)
                except Exception:
                    pass

        self._theta = self._theta_init.copy()

    def _calculate_slope(self) -> None:
        """Calculate slope from DEM."""
        dy, dx = np.gradient(self._dem, self._cellsize)
        self._slope = np.sqrt(dx**2 + dy**2)
        self._slope = np.maximum(self._slope, 0.001)

    def _create_simple_ldd(self) -> None:
        """Create simple local drain direction."""
        self._ldd = np.full((self._nrows, self._ncols), 2)  # Flow south
        self._ldd[-1, :] = 6  # Bottom row flows east
        self._ldd[-1, -1] = 5  # Outlet

    def update(self) -> None:
        """Advance the model by one time step."""
        if not self._initialized:
            raise RuntimeError("Model not initialized.")

        if self._current_time >= self._end_time:
            return

        dt = self._time_step

        # Add rainfall
        self._wh += self._rain * dt

        # Infiltration
        self._calculate_infiltration(dt)
        actual_infil = np.minimum(self._infil_rate * dt, self._wh)
        self._wh -= actual_infil
        self._infil_cum += actual_infil

        # Update soil moisture
        depth_factor = 0.3
        self._theta += actual_infil / depth_factor
        self._theta = np.minimum(self._theta, self._porosity)

        # ET
        et_actual = np.minimum(self._etp * dt, self._theta * depth_factor)
        self._theta -= et_actual / depth_factor
        self._theta = np.maximum(self._theta, 0.05)

        # Flow
        self._calculate_flow(dt)
        self._route_water(dt)

        self._runoff_vol = self._wh * self._cellsize**2
        self._current_time += dt

    def _calculate_infiltration(self, dt: float) -> None:
        """Calculate infiltration (Green-Ampt)."""
        delta_theta = np.maximum(self._porosity - self._theta, 0.01)
        f_cum_safe = np.maximum(self._infil_cum, 1e-6)
        f_pot = self._ksat * (1.0 + self._psi * delta_theta / f_cum_safe)
        self._infil_rate = np.minimum(f_pot, self._ksat * 2)
        self._infil_rate = np.minimum(self._infil_rate, self._wh / dt)

    def _calculate_flow(self, dt: float) -> None:
        """Calculate flow (Manning equation)."""
        h = np.maximum(self._wh, 0.0)
        h_power = np.power(h + 1e-10, 2.0/3.0)
        self._v = (1.0 / self._manning_n) * h_power * np.sqrt(self._slope)
        self._v = np.minimum(self._v, 5.0)
        self._q = self._v * h * self._cellsize

    def _route_water(self, dt: float) -> None:
        """Route water downstream."""
        wh_new = self._wh.copy()

        for i in range(self._nrows):
            for j in range(self._ncols):
                if self._wh[i, j] > 1e-6:
                    ldd = int(self._ldd[i, j])
                    if ldd == 5:
                        continue

                    di, dj = self._ldd_to_offset(ldd)
                    ni, nj = i + di, j + dj

                    if 0 <= ni < self._nrows and 0 <= nj < self._ncols:
                        flow_dist = self._v[i, j] * dt
                        flow_frac = min(flow_dist / self._cellsize, 0.5)
                        flow = self._wh[i, j] * flow_frac
                        wh_new[i, j] -= flow
                        wh_new[ni, nj] += flow

        self._wh = np.maximum(wh_new, 0.0)

    def _ldd_to_offset(self, ldd: int) -> tuple:
        """Convert LDD to offset."""
        offsets = {
            1: (1, -1), 2: (1, 0), 3: (1, 1),
            4: (0, -1), 5: (0, 0), 6: (0, 1),
            7: (-1, -1), 8: (-1, 0), 9: (-1, 1),
        }
        return offsets.get(ldd, (0, 0))

    def finalize(self) -> None:
        """Clean up resources."""
        self._initialized = False
        self._wh = None
        self._dem = None
        print("Model finalized.")

    # =========================================================================
    # BMI Info Functions
    # =========================================================================

    def get_component_name(self) -> str:
        return self._name

    def get_input_item_count(self) -> int:
        return len(self._input_var_names)

    def get_output_item_count(self) -> int:
        return len(self._output_var_names)

    def get_input_var_names(self) -> Tuple[str, ...]:
        return tuple(self._input_var_names)

    def get_output_var_names(self) -> Tuple[str, ...]:
        return tuple(self._output_var_names)

    # =========================================================================
    # BMI Variable Functions
    # =========================================================================

    def get_var_grid(self, name: str) -> int:
        self._check_var_name(name)
        return 0

    def get_var_type(self, name: str) -> str:
        self._check_var_name(name)
        return "float64"

    def get_var_units(self, name: str) -> str:
        self._check_var_name(name)
        return self._var_units.get(name, "-")

    def get_var_itemsize(self, name: str) -> int:
        self._check_var_name(name)
        return 8

    def get_var_nbytes(self, name: str) -> int:
        self._check_var_name(name)
        return self._nrows * self._ncols * 8

    def get_var_location(self, name: str) -> str:
        self._check_var_name(name)
        return "node"

    def _check_var_name(self, name: str) -> None:
        all_vars = set(self._input_var_names) | set(self._output_var_names)
        if name not in all_vars:
            raise ValueError(f"Unknown variable: {name}")

    # =========================================================================
    # BMI Time Functions
    # =========================================================================

    def get_current_time(self) -> float:
        return self._current_time

    def get_start_time(self) -> float:
        return self._start_time

    def get_end_time(self) -> float:
        return self._end_time

    def get_time_units(self) -> str:
        return self._time_units

    def get_time_step(self) -> float:
        return self._time_step

    # =========================================================================
    # BMI Grid Functions
    # =========================================================================

    def get_grid_rank(self, grid: int) -> int:
        return 2

    def get_grid_size(self, grid: int) -> int:
        return self._nrows * self._ncols

    def get_grid_type(self, grid: int) -> str:
        return "uniform_rectilinear"

    def get_grid_shape(self, grid: int, shape: np.ndarray) -> np.ndarray:
        shape[0] = self._nrows
        shape[1] = self._ncols
        return shape

    def get_grid_spacing(self, grid: int, spacing: np.ndarray) -> np.ndarray:
        spacing[0] = self._cellsize
        spacing[1] = self._cellsize
        return spacing

    def get_grid_origin(self, grid: int, origin: np.ndarray) -> np.ndarray:
        origin[0] = self._grid_origin[0]
        origin[1] = self._grid_origin[1]
        return origin

    def get_grid_x(self, grid: int, x: np.ndarray) -> np.ndarray:
        for i in range(self._ncols):
            x[i] = self._grid_origin[0] + i * self._cellsize
        return x

    def get_grid_y(self, grid: int, y: np.ndarray) -> np.ndarray:
        for i in range(self._nrows):
            y[i] = self._grid_origin[1] + i * self._cellsize
        return y

    def get_grid_z(self, grid: int, z: np.ndarray) -> np.ndarray:
        return z

    def get_grid_node_count(self, grid: int) -> int:
        return self.get_grid_size(grid)

    def get_grid_edge_count(self, grid: int) -> int:
        return (self._nrows - 1) * self._ncols + self._nrows * (self._ncols - 1)

    def get_grid_face_count(self, grid: int) -> int:
        return (self._nrows - 1) * (self._ncols - 1)

    # =========================================================================
    # BMI Getter Functions
    # =========================================================================

    def get_value(self, name: str, dest: np.ndarray) -> np.ndarray:
        """Get variable values."""
        self._check_var_name(name)
        src = self._get_var_array(name)
        dest[:] = src.flatten()
        return dest

    def get_value_ptr(self, name: str) -> np.ndarray:
        """Get reference to variable values."""
        self._check_var_name(name)
        return self._get_var_array(name).flatten()

    def get_value_at_indices(self, name: str, dest: np.ndarray,
                             inds: np.ndarray) -> np.ndarray:
        """Get values at specific indices."""
        self._check_var_name(name)
        src = self._get_var_array(name).flatten()
        dest[:] = src[inds]
        return dest

    def _get_var_array(self, name: str) -> np.ndarray:
        """Get internal array for variable."""
        var_map = {
            "water_surface__height": self._wh,
            "water_surface__discharge": self._q,
            "water_surface__velocity": self._v,
            "soil_water__infiltration_rate": self._infil_rate,
            "soil_water__cumulative_infiltration": self._infil_cum,
            "soil_water__content": self._theta,
            "surface_water__runoff_volume": self._runoff_vol,
            "land_surface__elevation": self._dem,
            "rainfall_rate": self._rain,
            "potential_evapotranspiration": self._etp,
            "channel_water__discharge": self._q,
        }
        arr = var_map.get(name)
        if arr is None:
            return np.zeros((self._nrows, self._ncols))
        return arr

    # =========================================================================
    # BMI Setter Functions
    # =========================================================================

    def set_value(self, name: str, src: np.ndarray) -> None:
        """Set variable values."""
        if name not in self._input_var_names:
            raise ValueError(f"Cannot set output variable: {name}")

        data = src.reshape((self._nrows, self._ncols))

        if name == "rainfall_rate":
            self._rain = data.copy()
        elif name == "potential_evapotranspiration":
            self._etp = data.copy()
        elif name == "water_surface__height":
            self._wh = data.copy()
        elif name == "soil_water__content":
            self._theta = data.copy()
        elif name == "land_surface__elevation":
            self._dem = data.copy()
            self._calculate_slope()

    def set_value_at_indices(self, name: str, inds: np.ndarray,
                             src: np.ndarray) -> None:
        """Set values at specific indices."""
        if name not in self._input_var_names:
            raise ValueError(f"Cannot set output variable: {name}")
        current = self._get_var_array(name).flatten()
        current[inds] = src
        self.set_value(name, current)

    # =========================================================================
    # Convenience methods
    # =========================================================================

    def update_until(self, time: float) -> None:
        """Advance until specified time."""
        while self._current_time < time and self._current_time < self._end_time:
            self.update()

    def set_rainfall_mm_h(self, rainfall_mm_h: np.ndarray) -> None:
        """Set rainfall in mm/h."""
        rainfall_m_s = rainfall_mm_h / (1000.0 * 3600.0)
        self.set_value("rainfall_rate", rainfall_m_s.flatten())

    def get_water_depth_mm(self) -> np.ndarray:
        """Get water depth in mm."""
        return self._wh * 1000.0

    def get_discharge_outlet(self) -> float:
        """Get outlet discharge."""
        return float(self._q[-1, -1])
