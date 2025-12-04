"""
Command-line interface for BMI OpenLISEM wrapper.
"""

import argparse
import sys
from pathlib import Path


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="BMI wrapper for OpenLISEM hydrological model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  bmi-openlisem run mymodel.run
  bmi-openlisem info mymodel.run
  bmi-openlisem validate mymodel.run
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run model simulation")
    run_parser.add_argument("runfile", type=str, help="Path to OpenLISEM runfile")
    run_parser.add_argument(
        "--steps", type=int, default=None,
        help="Number of time steps to run (default: run until end time)"
    )
    run_parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose output"
    )

    # Info command
    info_parser = subparsers.add_parser("info", help="Show configuration info")
    info_parser.add_argument("runfile", type=str, help="Path to OpenLISEM runfile")

    # Validate command
    val_parser = subparsers.add_parser("validate", help="Validate runfile and inputs")
    val_parser.add_argument("runfile", type=str, help="Path to OpenLISEM runfile")

    # Variables command
    var_parser = subparsers.add_parser("variables", help="List BMI variables")

    args = parser.parse_args()

    if args.command == "run":
        run_model(args)
    elif args.command == "info":
        show_info(args)
    elif args.command == "validate":
        validate_config(args)
    elif args.command == "variables":
        list_variables()
    else:
        parser.print_help()
        sys.exit(1)


def run_model(args):
    """Run the model simulation."""
    from .bmi_openlisem import BmiOpenLisem

    runfile = Path(args.runfile)
    if not runfile.exists():
        print(f"Error: Runfile not found: {runfile}")
        sys.exit(1)

    print(f"Initializing OpenLISEM BMI wrapper...")
    model = BmiOpenLisem()

    try:
        model.initialize(str(runfile))
        print(f"Model initialized successfully")
        print(f"  Start time: {model.get_start_time()} s")
        print(f"  End time: {model.get_end_time()} s")
        print(f"  Time step: {model.get_time_step()} s")
        print(f"  Grid shape: {model._grid_shape}")
        print()

        step = 0
        max_steps = args.steps

        while model.get_current_time() < model.get_end_time():
            if max_steps and step >= max_steps:
                break

            if args.verbose:
                print(f"Step {step + 1}: time = {model.get_current_time()} s")

            model.update()
            step += 1

            # Progress indicator
            if not args.verbose and step % 10 == 0:
                progress = (model.get_current_time() - model.get_start_time()) / \
                           (model.get_end_time() - model.get_start_time()) * 100
                print(f"\rProgress: {progress:.1f}%", end="", flush=True)

        print(f"\nSimulation completed: {step} steps")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        model.finalize()


def show_info(args):
    """Show configuration information."""
    from .config_manager import ConfigManager

    runfile = Path(args.runfile)
    if not runfile.exists():
        print(f"Error: Runfile not found: {runfile}")
        sys.exit(1)

    config = ConfigManager(str(runfile))

    print(f"OpenLISEM Configuration Info")
    print("=" * 50)
    print(f"Runfile: {runfile}")
    print()

    # Time parameters
    time_params = config.get_time_parameters()
    print("Time Parameters:")
    print(f"  Start time: {time_params['start_time']} s")
    print(f"  End time: {time_params['end_time']} s")
    print(f"  Time step: {time_params['timestep']} s")
    print(f"  Event based: {time_params['event_based']}")
    print()

    # Directories
    print("Directories:")
    print(f"  Input: {config.get_input_directory()}")
    print(f"  Results: {config.get_result_directory()}")
    print()

    # Switches
    switches = config.get_switches()
    print("Active Processes:")
    for name, enabled in switches.items():
        status = "enabled" if enabled else "disabled"
        print(f"  {name}: {status}")
    print()

    # Calibration
    cal_params = config.get_calibration_parameters()
    print("Calibration Parameters:")
    for name, value in cal_params.items():
        print(f"  {name}: {value}")


def validate_config(args):
    """Validate configuration and input files."""
    from .config_manager import ConfigManager
    from .map_io import MapIO

    runfile = Path(args.runfile)
    if not runfile.exists():
        print(f"Error: Runfile not found: {runfile}")
        sys.exit(1)

    print(f"Validating: {runfile}")
    print("=" * 50)

    errors = []
    warnings = []

    config = ConfigManager(str(runfile))
    map_io = MapIO(str(runfile.parent))

    # Check required maps
    required_maps = ["dem", "ldd"]
    for map_name in required_maps:
        map_path = config.get_map_path(map_name)
        if not map_path:
            errors.append(f"Required map not specified: {map_name}")
        elif not Path(map_path).exists():
            errors.append(f"Map file not found: {map_name} -> {map_path}")
        else:
            try:
                data, meta = map_io.read_map(map_path)
                print(f"  {map_name}: OK ({meta['nrows']}x{meta['ncols']})")
            except Exception as e:
                errors.append(f"Cannot read map {map_name}: {e}")

    # Check time parameters
    time_params = config.get_time_parameters()
    if time_params["end_time"] <= time_params["start_time"]:
        errors.append("End time must be greater than start time")
    if time_params["timestep"] <= 0:
        errors.append("Time step must be positive")

    # Report results
    print()
    if errors:
        print("ERRORS:")
        for e in errors:
            print(f"  - {e}")
    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"  - {w}")

    if not errors:
        print("Validation PASSED")
        sys.exit(0)
    else:
        print("Validation FAILED")
        sys.exit(1)


def list_variables():
    """List available BMI variables."""
    from .bmi_openlisem import BmiOpenLisem

    model = BmiOpenLisem()

    print("BMI OpenLISEM Variables")
    print("=" * 50)

    print("\nInput Variables:")
    for var in model._input_var_names:
        units = model._var_units.get(var, "-")
        internal = model._var_name_map.get(var, var)
        print(f"  {var}")
        print(f"    Units: {units}")
        print(f"    Internal: {internal}")

    print("\nOutput Variables:")
    for var in model._output_var_names:
        units = model._var_units.get(var, "-")
        internal = model._var_name_map.get(var, var)
        print(f"  {var}")
        print(f"    Units: {units}")
        print(f"    Internal: {internal}")


if __name__ == "__main__":
    main()
