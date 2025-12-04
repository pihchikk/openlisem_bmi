#!/usr/bin/env python3
"""
Example: Basic BMI usage for OpenLISEM

This example demonstrates how to use the BMI wrapper to run OpenLISEM
and access model variables during execution.
"""

import numpy as np
from pathlib import Path

# Import the BMI wrapper
from bmi_openlisem import BmiOpenLisem


def basic_simulation(runfile_path: str):
    """
    Run a basic OpenLISEM simulation using the BMI interface.

    Parameters
    ----------
    runfile_path : str
        Path to the OpenLISEM runfile (.run file)
    """
    print("=" * 60)
    print("OpenLISEM BMI Basic Simulation Example")
    print("=" * 60)

    # Create model instance
    model = BmiOpenLisem()

    try:
        # Initialize the model
        print(f"\nInitializing model from: {runfile_path}")
        model.initialize(runfile_path)

        # Print model information
        print(f"\nModel: {model.get_component_name()}")
        print(f"Start time: {model.get_start_time()} {model.get_time_units()}")
        print(f"End time: {model.get_end_time()} {model.get_time_units()}")
        print(f"Time step: {model.get_time_step()} {model.get_time_units()}")

        # Print grid information
        grid_id = 0
        shape = np.zeros(2, dtype=np.int32)
        model.get_grid_shape(grid_id, shape)
        print(f"\nGrid shape: {shape[0]} rows x {shape[1]} cols")
        print(f"Grid type: {model.get_grid_type(grid_id)}")

        # Print available variables
        print(f"\nInput variables ({model.get_input_item_count()}):")
        for var in model.get_input_var_names():
            print(f"  - {var} [{model.get_var_units(var)}]")

        print(f"\nOutput variables ({model.get_output_item_count()}):")
        for var in model.get_output_var_names():
            print(f"  - {var} [{model.get_var_units(var)}]")

        # Run the simulation
        print("\n" + "-" * 60)
        print("Running simulation...")
        print("-" * 60)

        step = 0
        total_steps = int((model.get_end_time() - model.get_start_time()) / model.get_time_step())

        while model.get_current_time() < model.get_end_time():
            # Update model by one timestep
            model.update()
            step += 1

            # Print progress every 10 steps
            if step % 10 == 0:
                progress = (model.get_current_time() / model.get_end_time()) * 100
                print(f"  Step {step}/{total_steps}: "
                      f"time = {model.get_current_time():.0f} s "
                      f"({progress:.1f}%)")

            # Optionally get output values
            if step % 20 == 0:
                # Get water height values
                wh = np.zeros(model.get_grid_size(0))
                model.get_value("water_surface__height", wh)
                wh_2d = wh.reshape(shape)

                # Print some statistics
                valid_wh = wh_2d[~np.isnan(wh_2d)]
                if len(valid_wh) > 0:
                    print(f"    Water height: max={np.max(valid_wh):.4f} m, "
                          f"mean={np.mean(valid_wh):.6f} m")

        print("\nSimulation completed!")
        print(f"Total steps: {step}")
        print(f"Final time: {model.get_current_time()} {model.get_time_units()}")

    except FileNotFoundError as e:
        print(f"\nError: {e}")
        print("Make sure the runfile and OpenLISEM executable exist.")
        return

    except Exception as e:
        print(f"\nError during simulation: {e}")
        raise

    finally:
        # Always finalize to clean up
        model.finalize()
        print("\nModel finalized.")


def coupling_example(runfile_path: str):
    """
    Example of model coupling: modifying inputs between timesteps.

    This demonstrates how to couple OpenLISEM with another model
    by modifying input variables during simulation.
    """
    print("=" * 60)
    print("OpenLISEM BMI Model Coupling Example")
    print("=" * 60)

    model = BmiOpenLisem()

    try:
        model.initialize(runfile_path)

        # Get grid size
        grid_size = model.get_grid_size(0)
        shape = np.zeros(2, dtype=np.int32)
        model.get_grid_shape(0, shape)

        print(f"\nGrid size: {grid_size} cells ({shape[0]}x{shape[1]})")

        # Simulate coupling with a hypothetical rainfall model
        print("\nSimulating rainfall model coupling...")

        step = 0
        while model.get_current_time() < model.get_end_time():
            # Example: Update rainfall from external source
            # In real coupling, this would come from another model

            if step % 5 == 0:  # Every 5 timesteps
                # Create spatially variable rainfall
                rain_rate = np.random.uniform(0, 0.0001, grid_size)  # m/s
                rain_rate = rain_rate.reshape(shape)

                # Set the rainfall in the model
                model.set_value("rainfall_rate", rain_rate.flatten())

                print(f"  Step {step}: Updated rainfall "
                      f"(mean={np.mean(rain_rate)*3600*1000:.2f} mm/h)")

            # Advance the model
            model.update()

            # Get runoff output for coupling to downstream model
            discharge = np.zeros(grid_size)
            model.get_value("water_surface__discharge", discharge)

            step += 1

        print(f"\nCoupling simulation completed after {step} steps")

    finally:
        model.finalize()


def data_access_example(runfile_path: str):
    """
    Example demonstrating various data access methods.
    """
    print("=" * 60)
    print("OpenLISEM BMI Data Access Example")
    print("=" * 60)

    model = BmiOpenLisem()

    try:
        model.initialize(runfile_path)

        grid_size = model.get_grid_size(0)
        shape = np.zeros(2, dtype=np.int32)
        model.get_grid_shape(0, shape)

        # Run a few timesteps
        for _ in range(5):
            model.update()

        # Method 1: get_value (copy to provided array)
        print("\n1. Using get_value():")
        wh_array = np.zeros(grid_size)
        model.get_value("water_surface__height", wh_array)
        print(f"   Water height array shape: {wh_array.shape}")
        print(f"   Non-NaN values: {np.sum(~np.isnan(wh_array))}")

        # Method 2: get_value_ptr (direct reference)
        print("\n2. Using get_value_ptr():")
        wh_ptr = model.get_value_ptr("water_surface__height")
        print(f"   Water height pointer shape: {wh_ptr.shape}")

        # Method 3: get_value_at_indices (specific cells)
        print("\n3. Using get_value_at_indices():")
        indices = np.array([0, 10, 100, 500])  # Specific cell indices
        values = np.zeros(len(indices))
        model.get_value_at_indices("water_surface__height", values, indices)
        print(f"   Values at indices {indices}: {values}")

        # Setting values
        print("\n4. Using set_value():")
        # Set initial water height for specific area
        new_wh = np.zeros((shape[0], shape[1]))
        new_wh[10:20, 10:20] = 0.01  # 1 cm water in a patch
        model.set_value("water_surface__height", new_wh.flatten())
        print("   Set water height for 10x10 cell patch")

        # Setting values at specific indices
        print("\n5. Using set_value_at_indices():")
        indices = np.array([100, 200, 300])
        new_values = np.array([0.05, 0.05, 0.05])  # 5 cm
        model.set_value_at_indices("water_surface__height", indices, new_values)
        print(f"   Set values at indices {indices}")

        # Grid information
        print("\n6. Grid information:")
        spacing = np.zeros(2)
        model.get_grid_spacing(0, spacing)
        print(f"   Grid spacing: {spacing}")

        origin = np.zeros(2)
        model.get_grid_origin(0, origin)
        print(f"   Grid origin: {origin}")

        print(f"   Grid rank: {model.get_grid_rank(0)}")
        print(f"   Grid node count: {model.get_grid_node_count(0)}")

    finally:
        model.finalize()


if __name__ == "__main__":
    import sys

    # Default runfile path (modify as needed)
    if len(sys.argv) > 1:
        runfile = sys.argv[1]
    else:
        # Try to find a runfile in common locations
        possible_paths = [
            "test.run",
            "example.run",
            "model.run",
            "../test/test.run",
        ]
        runfile = None
        for p in possible_paths:
            if Path(p).exists():
                runfile = p
                break

        if runfile is None:
            print("Usage: python bmi_example.py <path_to_runfile.run>")
            print("\nNo runfile specified and no default found.")
            print("Please provide a path to an OpenLISEM runfile.")
            sys.exit(1)

    # Run examples
    print("\n" + "=" * 60)
    print("EXAMPLE 1: Basic Simulation")
    basic_simulation(runfile)

    print("\n" + "=" * 60)
    print("EXAMPLE 2: Model Coupling")
    coupling_example(runfile)

    print("\n" + "=" * 60)
    print("EXAMPLE 3: Data Access")
    data_access_example(runfile)
