"""
Tests for the BMI OpenLISEM wrapper.

Run with: pytest tests/test_bmi_openlisem.py -v
"""

import pytest
import numpy as np
import tempfile
import os
from pathlib import Path


class TestBmiOpenLisemInit:
    """Test BMI initialization and basic properties."""

    def test_import(self):
        """Test that the package can be imported."""
        from bmi_openlisem import BmiOpenLisem
        assert BmiOpenLisem is not None

    def test_create_instance(self):
        """Test creating a BmiOpenLisem instance."""
        from bmi_openlisem import BmiOpenLisem
        model = BmiOpenLisem()
        assert model is not None
        assert model._initialized is False

    def test_component_name(self):
        """Test get_component_name before initialization."""
        from bmi_openlisem import BmiOpenLisem
        model = BmiOpenLisem()
        assert model.get_component_name() == "OpenLISEM"

    def test_var_names(self):
        """Test variable name retrieval."""
        from bmi_openlisem import BmiOpenLisem
        model = BmiOpenLisem()

        input_vars = model.get_input_var_names()
        assert len(input_vars) > 0
        assert "rainfall_rate" in input_vars

        output_vars = model.get_output_var_names()
        assert len(output_vars) > 0
        assert "water_surface__height" in output_vars

    def test_var_units(self):
        """Test variable unit retrieval."""
        from bmi_openlisem import BmiOpenLisem
        model = BmiOpenLisem()

        assert model.get_var_units("rainfall_rate") == "m/s"
        assert model.get_var_units("water_surface__height") == "m"
        assert model.get_var_units("water_surface__discharge") == "m3/s"

    def test_var_type(self):
        """Test variable type retrieval."""
        from bmi_openlisem import BmiOpenLisem
        model = BmiOpenLisem()

        assert model.get_var_type("rainfall_rate") == "float64"
        assert model.get_var_type("water_surface__height") == "float64"

    def test_invalid_var_name(self):
        """Test that invalid variable names raise errors."""
        from bmi_openlisem import BmiOpenLisem
        model = BmiOpenLisem()

        with pytest.raises(ValueError):
            model.get_var_units("invalid_variable_name")


class TestConfigManager:
    """Test configuration file management."""

    def test_import(self):
        """Test importing ConfigManager."""
        from bmi_openlisem import ConfigManager
        assert ConfigManager is not None

    def test_create_empty(self):
        """Test creating empty ConfigManager."""
        from bmi_openlisem import ConfigManager
        config = ConfigManager()
        assert config is not None

    def test_set_get_value(self):
        """Test setting and getting values."""
        from bmi_openlisem import ConfigManager
        config = ConfigManager()

        config.set_value("test_param", "123")
        assert config.get_value("test_param") == "123"

        # Test case insensitivity
        assert config.get_value("TEST_PARAM") == "123"
        assert config.get_value("Test_Param") == "123"

    def test_default_value(self):
        """Test default value for missing parameters."""
        from bmi_openlisem import ConfigManager
        config = ConfigManager()

        assert config.get_value("nonexistent") is None
        assert config.get_value("nonexistent", "default") == "default"

    def test_copy(self):
        """Test configuration copy."""
        from bmi_openlisem import ConfigManager
        config = ConfigManager()
        config.set_value("param1", "value1")

        config_copy = config.copy()
        assert config_copy.get_value("param1") == "value1"

        # Modify copy shouldn't affect original
        config_copy.set_value("param1", "modified")
        assert config.get_value("param1") == "value1"

    def test_write_read(self):
        """Test writing and reading configuration."""
        from bmi_openlisem import ConfigManager

        with tempfile.NamedTemporaryFile(mode='w', suffix='.run', delete=False) as f:
            temp_file = f.name

        try:
            # Create and write config
            config1 = ConfigManager()
            config1.set_value("Begin Time", "1:0")
            config1.set_value("End Time", "1:60")
            config1.set_value("Timestep", "10")
            config1._runfile_path = temp_file
            config1.write(temp_file)

            # Read config
            config2 = ConfigManager(temp_file)
            assert config2.get_value("begin time") == "1:0"
            assert config2.get_value("end time") == "1:60"
            assert config2.get_value("timestep") == "10"

        finally:
            os.unlink(temp_file)


class TestMapIO:
    """Test map I/O functionality."""

    def test_import(self):
        """Test importing MapIO."""
        from bmi_openlisem import MapIO
        assert MapIO is not None

    def test_create_instance(self):
        """Test creating MapIO instance."""
        from bmi_openlisem import MapIO
        io = MapIO()
        assert io is not None

    def test_write_read_ascii(self):
        """Test writing and reading ASCII grid."""
        from bmi_openlisem import MapIO

        io = MapIO()

        # Create test data
        data = np.random.rand(10, 15).astype(np.float64)
        data[2, 3] = np.nan  # Add missing value

        metadata = {
            "nrows": 10,
            "ncols": 15,
            "xllcorner": 100.0,
            "yllcorner": 200.0,
            "cellsize": 10.0,
        }

        with tempfile.NamedTemporaryFile(suffix='.asc', delete=False) as f:
            temp_file = f.name

        try:
            # Write and read
            io.write_map(temp_file, data, metadata, format="ascii")
            read_data, read_meta = io.read_map(temp_file)

            # Check data
            assert read_data.shape == data.shape
            np.testing.assert_array_almost_equal(
                read_data[~np.isnan(data)],
                data[~np.isnan(data)],
                decimal=5
            )

            # Check metadata
            assert read_meta["nrows"] == metadata["nrows"]
            assert read_meta["ncols"] == metadata["ncols"]
            assert read_meta["cellsize"] == metadata["cellsize"]

        finally:
            os.unlink(temp_file)

    def test_write_read_pcraster(self):
        """Test writing and reading PCRaster format."""
        from bmi_openlisem import MapIO

        io = MapIO()

        # Create test data
        data = np.random.rand(10, 15).astype(np.float64)

        metadata = {
            "nrows": 10,
            "ncols": 15,
            "xllcorner": 100.0,
            "yllcorner": 200.0,
            "cellsize": 10.0,
        }

        with tempfile.NamedTemporaryFile(suffix='.map', delete=False) as f:
            temp_file = f.name

        try:
            # Write and read
            io.write_map(temp_file, data, metadata, format="pcraster")
            read_data, read_meta = io.read_map(temp_file)

            # Check data (float32 precision)
            assert read_data.shape == data.shape
            np.testing.assert_array_almost_equal(
                read_data,
                data,
                decimal=5
            )

        finally:
            os.unlink(temp_file)

    def test_create_constant_map(self):
        """Test creating constant map from template."""
        from bmi_openlisem import MapIO

        io = MapIO()

        # Create template
        template_data = np.random.rand(10, 15)
        metadata = {"nrows": 10, "ncols": 15, "cellsize": 10.0,
                    "xllcorner": 0, "yllcorner": 0}

        with tempfile.NamedTemporaryFile(suffix='.asc', delete=False) as f:
            temp_file = f.name

        try:
            io.write_map(temp_file, template_data, metadata, format="ascii")

            # Create constant map
            const_map = io.create_constant_map(5.0, temp_file)

            assert const_map.shape == (10, 15)
            assert np.all(const_map == 5.0)

        finally:
            os.unlink(temp_file)


class TestBmiGridFunctions:
    """Test BMI grid-related functions."""

    def test_grid_type(self):
        """Test grid type."""
        from bmi_openlisem import BmiOpenLisem
        model = BmiOpenLisem()
        assert model.get_grid_type(0) == "uniform_rectilinear"

    def test_grid_rank(self):
        """Test grid rank."""
        from bmi_openlisem import BmiOpenLisem
        model = BmiOpenLisem()
        assert model.get_grid_rank(0) == 2


class TestBmiTimeFunctions:
    """Test BMI time-related functions."""

    def test_time_units(self):
        """Test time units."""
        from bmi_openlisem import BmiOpenLisem
        model = BmiOpenLisem()
        assert model.get_time_units() == "s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
