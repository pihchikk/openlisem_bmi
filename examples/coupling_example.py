#!/usr/bin/env python3
"""
Example: Model Coupling with BMI OpenLISEM

This example demonstrates how to couple OpenLISEM with other models
using the BMI interface for model coupling experiments.

Common coupling scenarios:
1. Weather model -> OpenLISEM (rainfall forcing)
2. OpenLISEM -> River routing model (discharge output)
3. Groundwater model <-> OpenLISEM (bidirectional coupling)
"""

import numpy as np
from pathlib import Path
from typing import Optional


class SimpleRainfallModel:
    """
    A simple synthetic rainfall model for demonstration.

    This represents an external weather/rainfall model that could
    provide spatially distributed rainfall to OpenLISEM.
    """

    def __init__(self, nrows: int, ncols: int, cellsize: float):
        self.nrows = nrows
        self.ncols = ncols
        self.cellsize = cellsize
        self.time = 0.0
        self._dt = 60.0  # 1 minute timestep

        # Storm parameters
        self.storm_center = (nrows // 2, ncols // 2)
        self.storm_radius = min(nrows, ncols) // 4
        self.peak_intensity = 50.0  # mm/h
        self.storm_duration = 3600.0  # 1 hour
        self.storm_start = 600.0  # Start after 10 minutes

    def update(self) -> None:
        """Advance the rainfall model by one timestep."""
        self.time += self._dt

    def get_rainfall(self) -> np.ndarray:
        """
        Get current rainfall intensity.

        Returns
        -------
        np.ndarray
            Rainfall rate in m/s (shape: nrows x ncols)
        """
        rain = np.zeros((self.nrows, self.ncols))

        # Check if within storm period
        if self.time < self.storm_start:
            return rain

        elapsed = self.time - self.storm_start
        if elapsed > self.storm_duration:
            return rain

        # Time-varying intensity (trapezoidal hyetograph)
        rise_time = self.storm_duration * 0.3
        fall_time = self.storm_duration * 0.3

        if elapsed < rise_time:
            intensity_factor = elapsed / rise_time
        elif elapsed > self.storm_duration - fall_time:
            intensity_factor = (self.storm_duration - elapsed) / fall_time
        else:
            intensity_factor = 1.0

        # Spatial distribution (Gaussian around storm center)
        y, x = np.ogrid[:self.nrows, :self.ncols]
        cy, cx = self.storm_center
        distance = np.sqrt((y - cy)**2 + (x - cx)**2)

        spatial_factor = np.exp(-(distance / self.storm_radius)**2)

        # Calculate rainfall in m/s
        intensity_mm_h = self.peak_intensity * intensity_factor * spatial_factor
        rain = intensity_mm_h / (1000.0 * 3600.0)  # Convert mm/h to m/s

        return rain


class SimpleDownstreamModel:
    """
    A simple downstream receiving model for demonstration.

    This represents a model that receives discharge from OpenLISEM
    outlets, like a river routing or reservoir model.
    """

    def __init__(self, num_outlets: int):
        self.num_outlets = num_outlets
        self.time = 0.0
        self._dt = 60.0

        # Storage for each outlet
        self.storage = np.zeros(num_outlets)
        self.inflow_history = []

    def update(self, inflows: np.ndarray) -> None:
        """
        Update the downstream model with inflows from OpenLISEM.

        Parameters
        ----------
        inflows : np.ndarray
            Discharge from each outlet [m3/s]
        """
        self.time += self._dt

        # Simple linear reservoir routing
        k = 0.1  # Recession constant
        self.storage = self.storage * np.exp(-k * self._dt) + inflows * self._dt

        self.inflow_history.append({
            'time': self.time,
            'inflows': inflows.copy(),
            'storage': self.storage.copy()
        })

    def get_outflow(self) -> np.ndarray:
        """Get current outflow from each reservoir."""
        k = 0.1
        return k * self.storage


def run_coupled_simulation(runfile_path: str, duration: Optional[float] = None):
    """
    Run a coupled simulation with OpenLISEM.

    Parameters
    ----------
    runfile_path : str
        Path to OpenLISEM runfile
    duration : float, optional
        Simulation duration in seconds (uses model end time if None)
    """
    from bmi_openlisem import BmiOpenLisem

    print("=" * 70)
    print("Coupled Model Simulation: Weather -> OpenLISEM -> Downstream")
    print("=" * 70)

    # Initialize OpenLISEM
    lisem = BmiOpenLisem()
    lisem.initialize(runfile_path)

    # Get grid information
    shape = np.zeros(2, dtype=np.int32)
    lisem.get_grid_shape(0, shape)
    nrows, ncols = int(shape[0]), int(shape[1])

    spacing = np.zeros(2)
    lisem.get_grid_spacing(0, spacing)
    cellsize = spacing[0]

    print(f"\nOpenLISEM grid: {nrows} x {ncols}, cellsize: {cellsize} m")

    # Initialize coupled models
    rainfall_model = SimpleRainfallModel(nrows, ncols, cellsize)
    downstream_model = SimpleDownstreamModel(num_outlets=1)

    # Determine simulation duration
    if duration is None:
        end_time = lisem.get_end_time()
    else:
        end_time = min(lisem.get_start_time() + duration, lisem.get_end_time())

    dt = lisem.get_time_step()
    print(f"Simulation: {lisem.get_start_time()} to {end_time} s, dt={dt} s")

    # Storage for results
    results = {
        'time': [],
        'rainfall_mean': [],
        'rainfall_max': [],
        'runoff_total': [],
        'wh_max': [],
        'discharge_outlet': [],
    }

    # Main time loop
    print("\nRunning coupled simulation...")
    step = 0

    try:
        while lisem.get_current_time() < end_time:
            current_time = lisem.get_current_time()

            # 1. Get rainfall from weather model
            rainfall_model.update()
            rainfall = rainfall_model.get_rainfall()

            # 2. Apply rainfall to OpenLISEM
            lisem.set_value("rainfall_rate", rainfall.flatten())

            # 3. Advance OpenLISEM
            lisem.update()

            # 4. Get outputs from OpenLISEM
            grid_size = lisem.get_grid_size(0)
            wh = np.zeros(grid_size)
            discharge = np.zeros(grid_size)

            lisem.get_value("water_surface__height", wh)
            lisem.get_value("water_surface__discharge", discharge)

            wh_2d = wh.reshape((nrows, ncols))
            discharge_2d = discharge.reshape((nrows, ncols))

            # 5. Get outlet discharge (assume last row, middle column)
            outlet_discharge = discharge_2d[-1, ncols // 2]

            # 6. Pass to downstream model
            downstream_model.update(np.array([outlet_discharge]))

            # Store results
            results['time'].append(current_time)
            results['rainfall_mean'].append(np.mean(rainfall) * 3600 * 1000)  # mm/h
            results['rainfall_max'].append(np.max(rainfall) * 3600 * 1000)
            results['runoff_total'].append(np.nansum(wh_2d) * cellsize**2)  # m3
            results['wh_max'].append(np.nanmax(wh_2d))
            results['discharge_outlet'].append(outlet_discharge)

            step += 1

            # Progress output
            if step % 20 == 0:
                print(f"  Time: {current_time:6.0f} s | "
                      f"Rain: {results['rainfall_mean'][-1]:5.1f} mm/h | "
                      f"WH max: {results['wh_max'][-1]:.4f} m | "
                      f"Q out: {outlet_discharge:.4f} m3/s")

    finally:
        lisem.finalize()

    # Print summary
    print("\n" + "-" * 70)
    print("Simulation Summary")
    print("-" * 70)
    print(f"Total steps: {step}")
    print(f"Peak rainfall: {max(results['rainfall_max']):.1f} mm/h")
    print(f"Max water height: {max(results['wh_max']):.4f} m")
    print(f"Peak outlet discharge: {max(results['discharge_outlet']):.4f} m3/s")

    # Save results if matplotlib available
    try:
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)

        times = np.array(results['time']) / 60  # Convert to minutes

        axes[0].fill_between(times, results['rainfall_mean'], alpha=0.7)
        axes[0].set_ylabel('Rainfall (mm/h)')
        axes[0].set_title('Coupled Simulation Results')

        axes[1].plot(times, results['wh_max'], 'b-')
        axes[1].set_ylabel('Max Water Height (m)')

        axes[2].plot(times, results['discharge_outlet'], 'r-')
        axes[2].set_ylabel('Outlet Discharge (m3/s)')
        axes[2].set_xlabel('Time (minutes)')

        plt.tight_layout()
        output_file = Path(runfile_path).parent / 'coupling_results.png'
        plt.savefig(output_file, dpi=150)
        print(f"\nResults plot saved to: {output_file}")

    except ImportError:
        print("\nNote: Install matplotlib to generate results plots")

    return results


def bidirectional_coupling_example(runfile_path: str):
    """
    Example of bidirectional coupling (e.g., with groundwater model).

    This demonstrates how to:
    1. Get infiltration from OpenLISEM
    2. Pass to a groundwater model
    3. Get groundwater feedback
    4. Modify OpenLISEM soil moisture
    """
    from bmi_openlisem import BmiOpenLisem

    print("=" * 70)
    print("Bidirectional Coupling: OpenLISEM <-> Groundwater Model")
    print("=" * 70)

    # Initialize OpenLISEM
    lisem = BmiOpenLisem()
    lisem.initialize(runfile_path)

    shape = np.zeros(2, dtype=np.int32)
    lisem.get_grid_shape(0, shape)
    nrows, ncols = int(shape[0]), int(shape[1])
    grid_size = lisem.get_grid_size(0)

    print(f"\nGrid: {nrows} x {ncols}")

    # Simple groundwater state
    gw_level = np.zeros((nrows, ncols))  # meters below surface
    gw_level[:] = 2.0  # Initial 2m depth

    step = 0
    max_steps = 100

    try:
        while lisem.get_current_time() < lisem.get_end_time() and step < max_steps:
            # 1. Get infiltration from OpenLISEM
            infil_vol = np.zeros(grid_size)
            lisem.get_value("soil_water__infiltration_volume", infil_vol)
            infil_2d = infil_vol.reshape((nrows, ncols))

            # 2. Update groundwater (simple model)
            # Infiltration raises water table
            specific_yield = 0.1
            cellsize = 10.0  # assume 10m cells
            cell_area = cellsize ** 2

            # Convert volume to depth and raise GW
            infil_depth = infil_2d / cell_area / specific_yield
            gw_level = np.maximum(0.1, gw_level - infil_depth)

            # Lateral groundwater flow (very simplified)
            gw_level = 0.99 * gw_level + 0.01 * np.mean(gw_level)

            # 3. Feedback to OpenLISEM
            # Adjust soil moisture based on GW depth
            # Shallow GW -> higher soil moisture
            moisture_feedback = np.clip(1.0 - gw_level / 3.0, 0.2, 0.9)

            # Set soil moisture
            lisem.set_value("soil_water__initial_content", moisture_feedback.flatten())

            # 4. Advance OpenLISEM
            lisem.update()

            step += 1

            if step % 10 == 0:
                print(f"  Step {step}: GW depth mean={np.mean(gw_level):.3f} m, "
                      f"Soil moisture mean={np.mean(moisture_feedback):.3f}")

    finally:
        lisem.finalize()

    print(f"\nCompleted {step} bidirectional coupling steps")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python coupling_example.py <runfile.run> [duration_seconds]")
        print("\nThis example demonstrates model coupling with OpenLISEM.")
        sys.exit(1)

    runfile = sys.argv[1]
    duration = float(sys.argv[2]) if len(sys.argv) > 2 else None

    # Run the coupled simulation
    results = run_coupled_simulation(runfile, duration)

    print("\n" + "=" * 70)
    print("Running bidirectional coupling example...")
    bidirectional_coupling_example(runfile)
