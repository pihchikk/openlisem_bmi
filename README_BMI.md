# BMI Wrapper for OpenLISEM

A Python Basic Model Interface (BMI) wrapper for the OpenLISEM spatial surface water balance and soil erosion model.

## Overview

This package provides a [CSDMS BMI 2.0](https://bmi.readthedocs.io/) compliant wrapper for OpenLISEM, enabling:

- **Model coupling** with other BMI-compliant models
- **Programmatic control** of model execution from Python
- **Runtime data access** to model variables
- **Integration** with modeling frameworks like pymt, Landlab, etc.

## Features

- Full BMI 2.0 specification support
- Support for PCRaster, GeoTIFF, and ASCII grid formats
- Configuration file management
- Command-line interface
- Example scripts for common use cases

## Installation

### Prerequisites

1. **OpenLISEM executable**: Build OpenLISEM from source or download a precompiled binary
2. **Python 3.8+**
3. **NumPy**

### Install from source

```bash
cd openlisem_bmi
pip install -e .
```

### Install with optional dependencies

```bash
# With GDAL support for GeoTIFF
pip install -e ".[gdal]"

# Full installation
pip install -e ".[full]"
```

### Set OpenLISEM path

Set the path to the OpenLISEM executable:

```bash
export OPENLISEM_EXECUTABLE=/path/to/Lisem
```

Or ensure `Lisem` is in your PATH.

## Quick Start

### Basic Usage

```python
from bmi_openlisem import BmiOpenLisem

# Create and initialize model
model = BmiOpenLisem()
model.initialize("path/to/your/runfile.run")

# Run simulation
while model.get_current_time() < model.get_end_time():
    model.update()

# Clean up
model.finalize()
```

### Accessing Variables

```python
import numpy as np

# Get grid information
grid_size = model.get_grid_size(0)
shape = np.zeros(2, dtype=np.int32)
model.get_grid_shape(0, shape)

# Read output variable
water_height = np.zeros(grid_size)
model.get_value("water_surface__height", water_height)

# Set input variable
rainfall = np.full(grid_size, 0.00001)  # m/s
model.set_value("rainfall_rate", rainfall)
```

### Model Coupling Example

```python
from bmi_openlisem import BmiOpenLisem

# Initialize OpenLISEM
lisem = BmiOpenLisem()
lisem.initialize("model.run")

# Coupling loop
while lisem.get_current_time() < lisem.get_end_time():
    # Get rainfall from external model
    rainfall = get_rainfall_from_weather_model()
    lisem.set_value("rainfall_rate", rainfall)

    # Advance OpenLISEM
    lisem.update()

    # Get discharge for downstream model
    discharge = np.zeros(lisem.get_grid_size(0))
    lisem.get_value("water_surface__discharge", discharge)

    # Pass to downstream model
    send_to_river_model(discharge)

lisem.finalize()
```

## BMI Functions

### Model Control

| Function | Description |
|----------|-------------|
| `initialize(config_file)` | Initialize from runfile |
| `update()` | Advance by one timestep |
| `update_until(time)` | Advance to specified time |
| `finalize()` | Clean up resources |

### Model Information

| Function | Description |
|----------|-------------|
| `get_component_name()` | Returns "OpenLISEM" |
| `get_input_var_names()` | List of input variables |
| `get_output_var_names()` | List of output variables |

### Variable Information

| Function | Description |
|----------|-------------|
| `get_var_type(name)` | Data type (float64) |
| `get_var_units(name)` | Variable units |
| `get_var_grid(name)` | Grid identifier |
| `get_var_nbytes(name)` | Size in bytes |

### Time Functions

| Function | Description |
|----------|-------------|
| `get_current_time()` | Current model time (s) |
| `get_start_time()` | Simulation start time (s) |
| `get_end_time()` | Simulation end time (s) |
| `get_time_step()` | Model timestep (s) |
| `get_time_units()` | Time units ("s") |

### Grid Functions

| Function | Description |
|----------|-------------|
| `get_grid_type(grid)` | Grid type |
| `get_grid_rank(grid)` | Number of dimensions |
| `get_grid_shape(grid, shape)` | Grid dimensions |
| `get_grid_spacing(grid, spacing)` | Cell size |
| `get_grid_origin(grid, origin)` | Grid origin |

### Data Access

| Function | Description |
|----------|-------------|
| `get_value(name, dest)` | Copy values to array |
| `get_value_ptr(name)` | Get reference to values |
| `get_value_at_indices(name, dest, inds)` | Get specific cells |
| `set_value(name, src)` | Set variable values |
| `set_value_at_indices(name, inds, src)` | Set specific cells |

## Available Variables

### Input Variables

| BMI Name | Units | Description |
|----------|-------|-------------|
| `rainfall_rate` | m/s | Rainfall intensity |
| `potential_evapotranspiration` | m/s | ET rate |
| `water_surface__height` | m | Surface water height |
| `soil_water__initial_content` | - | Initial soil moisture |
| `land_surface__elevation` | m | DEM |

### Output Variables

| BMI Name | Units | Description |
|----------|-------|-------------|
| `water_surface__height` | m | Water height on surface |
| `water_surface__discharge` | m³/s | Discharge |
| `water_surface__velocity` | m/s | Flow velocity |
| `soil_water__infiltration_volume` | m³ | Infiltration volume |
| `soil_water__content` | - | Soil moisture |
| `sediment__concentration` | kg/m³ | Sediment concentration |
| `sediment__mass_flux` | kg/s | Sediment flux |
| `channel_water__height` | m | Channel water height |
| `channel_water__discharge` | m³/s | Channel discharge |

## Command-Line Interface

```bash
# Run a simulation
bmi-openlisem run mymodel.run

# Show configuration info
bmi-openlisem info mymodel.run

# Validate configuration
bmi-openlisem validate mymodel.run

# List available variables
bmi-openlisem variables
```

## Configuration

The wrapper uses OpenLISEM runfiles (`.run` files) for configuration. See the OpenLISEM documentation for runfile format details.

### Key Configuration Parameters

```
Begin Time = 1:0
End Time = 1:120
Timestep = 10

dem = input/dem.map
ldd = input/ldd.map
...
```

## Examples

See the `examples/` directory for complete examples:

- `bmi_example.py` - Basic BMI usage
- `coupling_example.py` - Model coupling scenarios

## Limitations

1. **Subprocess-based**: Each timestep runs OpenLISEM as a subprocess, which has overhead
2. **File-based exchange**: Data is exchanged through map files
3. **No sub-timestep control**: Cannot advance by fractions of a timestep

For tighter integration, consider the native C++ BMI implementation (future work).

## License

GPLv3 (same as OpenLISEM)

## References

- [OpenLISEM](https://github.com/vjetten/openlisem)
- [BMI Specification](https://bmi.readthedocs.io/)
- [CSDMS](https://csdms.colorado.edu/)

## Authors

- OpenLISEM: Victor Jetten (v.g.jetten@utwente.nl)
- BMI Wrapper: Created with Claude AI assistance
