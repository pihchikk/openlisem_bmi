# Troubleshooting Installation Issues

## Fixed: "Multiple top-level packages discovered" Error

**Issue**: The original error you encountered was:
```
error: Multiple top-level packages discovered in a flat-layout: ['bmi', 'PCR', 'pest', ...]
```

**Fix Applied**: Updated `setup.py` and `pyproject.toml` to explicitly set `packages=[]`, which tells setuptools that this package only contains a C++ extension module, not Python packages.

## Installation Methods

### Method 1: Using pip (Recommended)

```bash
cd /home/user/openlisem_bmi
pip install -e .
```

### Method 2: Using the installation script

```bash
cd /home/user/openlisem_bmi
./install_and_test.sh
```

This script will:
- Check all dependencies
- Install missing Python packages
- Clean previous builds
- Attempt installation
- Test the module

### Method 3: Manual CMake build

If pip installation still fails, try manual build:

```bash
cd /home/user/openlisem_bmi
mkdir -p build && cd build
cmake .. -DBUILD_BMI=ON -DCMAKE_BUILD_TYPE=Release
make -j4
```

Then add to Python path:
```bash
export PYTHONPATH=/home/user/openlisem_bmi/build/bmi:$PYTHONPATH
```

## Common Issues and Solutions

### Issue 1: Qt6 not found

**Error**: `Could not find a package configuration file provided by "Qt6"`

**Solution**:
```bash
# Find Qt6 installation
find /usr -name Qt6Config.cmake 2>/dev/null

# Set Qt6 path (adjust path as needed)
export Qt6_DIR=/usr/lib/x86_64-linux-gnu/cmake/Qt6

# Or install Qt6
sudo apt-get install qt6-base-dev
```

### Issue 2: GDAL not found

**Error**: `Could not find GDAL`

**Solution**:
```bash
sudo apt-get install libgdal-dev
# Or
export GDAL_DIR=/usr/lib/x86_64-linux-gnu/cmake/GDAL
```

### Issue 3: pybind11 not found

**Error**: `Could not find pybind11`

**Solution**:
```bash
pip3 install pybind11

# If that doesn't work, install from apt
sudo apt-get install pybind11-dev
```

### Issue 4: OpenMP not found

**Error**: `Could not find OpenMP`

**Solution**:
```bash
sudo apt-get install libomp-dev
```

### Issue 5: Build fails with compiler errors

**Solution**: Make sure you have a C++17 compatible compiler
```bash
# Check GCC version (need >= 7.0)
gcc --version

# Update if needed
sudo apt-get install gcc-9 g++-9
export CC=gcc-9
export CXX=g++-9
```

### Issue 6: ImportError after successful build

**Error**: `ImportError: cannot import name 'bmi_openlisem'`

**Solution**:
```bash
# Check if the module was built
find build -name "bmi_openlisem*.so"

# If found, add to Python path
export PYTHONPATH=/home/user/openlisem_bmi/build/bmi:$PYTHONPATH

# Or reinstall
pip3 uninstall bmi-openlisem
pip3 install -e .
```

### Issue 7: Shared library errors at runtime

**Error**: `error while loading shared libraries: libQt6Core.so.6`

**Solution**:
```bash
# Add Qt6 to library path
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH

# Or find Qt6 libs
find /usr -name "libQt6Core.so*" 2>/dev/null
export LD_LIBRARY_PATH=/path/to/qt6/libs:$LD_LIBRARY_PATH
```

## Verification Steps

After installation, verify it works:

```python
# Test 1: Import module
import bmi_openlisem
print("✓ Import successful")

# Test 2: Create instance
model = bmi_openlisem.BmiOpenLISEM()
print(f"✓ Component: {model.get_component_name()}")

# Test 3: Check variables
print(f"✓ Available variables: {len(model.get_output_var_names())}")
```

## Full Dependency List

For reference, here's what you need installed:

### System packages (Ubuntu/Debian):
```bash
sudo apt-get install -y \
    build-essential \
    cmake \
    git \
    qt6-base-dev \
    libgdal-dev \
    libssl-dev \
    libcurl4-openssl-dev \
    libomp-dev \
    python3-dev \
    python3-pip
```

### Python packages:
```bash
pip3 install numpy pybind11
```

## Still Having Issues?

1. **Clean everything and start fresh**:
   ```bash
   cd /home/user/openlisem_bmi
   rm -rf build dist *.egg-info
   pip3 uninstall bmi-openlisem
   ```

2. **Try the automated script**:
   ```bash
   ./install_and_test.sh
   ```

3. **Check the build log**:
   ```bash
   pip install -e . --verbose 2>&1 | tee install.log
   ```

4. **Try without pybind11 autodiscovery**:
   ```bash
   export pybind11_DIR=$(python3 -m pybind11 --cmakedir)
   pip install -e .
   ```

## Environment Setup for Development

If you're doing development work:

```bash
# Add to your ~/.bashrc or ~/.zshrc
export OPENLISEM_BMI=/home/user/openlisem_bmi
export PYTHONPATH=$OPENLISEM_BMI/build/bmi:$PYTHONPATH
export LD_LIBRARY_PATH=$OPENLISEM_BMI/build/bmi:$LD_LIBRARY_PATH

# Qt6 path (adjust as needed)
export Qt6_DIR=/usr/lib/x86_64-linux-gnu/cmake/Qt6

# For development builds
alias build_bmi="cd $OPENLISEM_BMI/build && cmake .. -DBUILD_BMI=ON && make -j4"
```

## Success Indicators

You know installation worked when:

1. ✓ `pip install -e .` completes without errors
2. ✓ `python3 -c "import bmi_openlisem"` works
3. ✓ `find build -name "bmi_openlisem*.so"` shows the compiled module
4. ✓ Example scripts run: `python3 examples/test_bmi_simple.py runfile.run`

## Contact

If you're still stuck after trying these solutions, please provide:
- Full error message
- Output of `cmake --version`, `python3 --version`, `gcc --version`
- Operating system and version
- Output of `pip install -e . --verbose`
