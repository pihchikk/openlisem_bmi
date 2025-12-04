#!/bin/bash
#
# Installation troubleshooting and test script
# This script helps diagnose and fix common installation issues
#

set -e

echo "============================================"
echo "openLISEM BMI Installation Troubleshooting"
echo "============================================"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python version
echo -e "${YELLOW}Checking Python version...${NC}"
python3 --version
if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: Python 3 not found!${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python OK${NC}"
echo ""

# Check pip
echo -e "${YELLOW}Checking pip...${NC}"
pip3 --version
if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: pip3 not found!${NC}"
    exit 1
fi
echo -e "${GREEN}✓ pip OK${NC}"
echo ""

# Check CMake
echo -e "${YELLOW}Checking CMake...${NC}"
cmake --version
if [ $? -ne 0 ]; then
    echo -e "${RED}ERROR: CMake not found!${NC}"
    echo "Install with: sudo apt-get install cmake"
    exit 1
fi
echo -e "${GREEN}✓ CMake OK${NC}"
echo ""

# Check for Qt6
echo -e "${YELLOW}Checking Qt6...${NC}"
if pkg-config --exists Qt6Core 2>/dev/null; then
    echo -e "${GREEN}✓ Qt6 found${NC}"
elif command -v qmake6 &> /dev/null; then
    echo -e "${GREEN}✓ Qt6 found (via qmake6)${NC}"
else
    echo -e "${YELLOW}WARNING: Qt6 not detected${NC}"
    echo "Install with: sudo apt-get install qt6-base-dev"
fi
echo ""

# Check for GDAL
echo -e "${YELLOW}Checking GDAL...${NC}"
if pkg-config --exists gdal 2>/dev/null; then
    echo -e "${GREEN}✓ GDAL found${NC}"
elif command -v gdal-config &> /dev/null; then
    echo -e "${GREEN}✓ GDAL found (via gdal-config)${NC}"
else
    echo -e "${YELLOW}WARNING: GDAL not detected${NC}"
    echo "Install with: sudo apt-get install libgdal-dev"
fi
echo ""

# Check for pybind11
echo -e "${YELLOW}Checking pybind11...${NC}"
python3 -c "import pybind11" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ pybind11 found${NC}"
else
    echo -e "${YELLOW}WARNING: pybind11 not found${NC}"
    echo "Installing pybind11..."
    pip3 install pybind11
fi
echo ""

# Check numpy
echo -e "${YELLOW}Checking numpy...${NC}"
python3 -c "import numpy" 2>/dev/null
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ numpy found${NC}"
else
    echo -e "${YELLOW}WARNING: numpy not found${NC}"
    echo "Installing numpy..."
    pip3 install numpy
fi
echo ""

# Clean previous build
echo -e "${YELLOW}Cleaning previous build...${NC}"
rm -rf build dist *.egg-info
echo -e "${GREEN}✓ Cleaned${NC}"
echo ""

# Try installation
echo "============================================"
echo -e "${YELLOW}Attempting installation...${NC}"
echo "============================================"
echo ""

pip3 install -e . --verbose

if [ $? -eq 0 ]; then
    echo ""
    echo "============================================"
    echo -e "${GREEN}Installation successful!${NC}"
    echo "============================================"
    echo ""

    # Test import
    echo -e "${YELLOW}Testing module import...${NC}"
    python3 -c "import bmi_openlisem; print('✓ Import successful')"

    if [ $? -eq 0 ]; then
        echo ""
        echo -e "${GREEN}All tests passed!${NC}"
        echo ""
        echo "You can now use the BMI wrapper:"
        echo "  import bmi_openlisem"
        echo "  model = bmi_openlisem.BmiOpenLISEM()"
        echo ""
        echo "See examples/ directory for usage examples."
    else
        echo -e "${RED}Import failed!${NC}"
        echo "Check that the shared library was built correctly."
        exit 1
    fi
else
    echo ""
    echo "============================================"
    echo -e "${RED}Installation failed!${NC}"
    echo "============================================"
    echo ""
    echo "Common issues and solutions:"
    echo ""
    echo "1. Missing dependencies:"
    echo "   sudo apt-get install -y build-essential cmake qt6-base-dev libgdal-dev"
    echo ""
    echo "2. pybind11 not found:"
    echo "   pip3 install pybind11"
    echo ""
    echo "3. Qt6 in non-standard location:"
    echo "   export CMAKE_PREFIX_PATH=/path/to/qt6"
    echo ""
    echo "4. Try manual build:"
    echo "   mkdir build && cd build"
    echo "   cmake .. -DBUILD_BMI=ON"
    echo "   make -j4"
    echo ""
    exit 1
fi
