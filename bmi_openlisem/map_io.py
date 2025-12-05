"""
Map I/O utilities for OpenLISEM BMI wrapper.

Handles reading and writing of spatial data in various formats:
- PCRaster map format (.map) via GDAL
- GeoTIFF format (.tif, .tiff)
- ASCII grid format (.asc)
"""

import os
import numpy as np
from typing import Tuple, Dict, Any
from pathlib import Path


class MapIO:
    """
    Map I/O handler for OpenLISEM spatial data.

    Uses GDAL for reliable reading of PCRaster and other formats.
    Falls back to simple ASCII reader if GDAL not available.
    """

    def __init__(self, base_dir: str = "."):
        self.base_dir = base_dir
        self._gdal_available = self._check_gdal()

    def _check_gdal(self) -> bool:
        """Check if GDAL is available."""
        try:
            from osgeo import gdal
            gdal.UseExceptions()
            return True
        except ImportError:
            return False

    def read_map(self, filepath: str) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        Read a map file.

        Parameters
        ----------
        filepath : str
            Path to the map file

        Returns
        -------
        tuple
            (data array, metadata dictionary)
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise FileNotFoundError(f"Map file not found: {filepath}")

        ext = filepath.suffix.lower()

        # Use GDAL for all formats if available (most reliable)
        if self._gdal_available:
            return self._read_gdal(filepath)
        elif ext == ".asc":
            return self._read_ascii_grid(filepath)
        else:
            raise ValueError(
                f"GDAL not available. Cannot read {ext} files. "
                "Install GDAL: pip install GDAL"
            )

    def write_map(self, filepath: str, data: np.ndarray,
                  metadata: Dict[str, Any], format: str = "auto") -> None:
        """Write a map file."""
        filepath = Path(filepath)

        if format == "auto":
            ext = filepath.suffix.lower()
            if ext == ".asc":
                format = "ascii"
            elif ext in [".tif", ".tiff"]:
                format = "geotiff"
            else:
                format = "geotiff"  # Default to GeoTIFF

        if format == "ascii":
            self._write_ascii_grid(filepath, data, metadata)
        elif format == "geotiff" and self._gdal_available:
            self._write_geotiff(filepath, data, metadata)
        elif format == "geotiff":
            # Fallback to ASCII if no GDAL
            ascii_path = filepath.with_suffix('.asc')
            self._write_ascii_grid(ascii_path, data, metadata)
        else:
            raise ValueError(f"Unknown format: {format}")

    def _read_gdal(self, filepath: Path) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Read any raster format using GDAL."""
        from osgeo import gdal

        ds = gdal.Open(str(filepath))
        if ds is None:
            raise IOError(f"Could not open file: {filepath}")

        band = ds.GetRasterBand(1)
        data = band.ReadAsArray().astype(np.float64)

        # Get geotransform: (xmin, xres, 0, ymax, 0, -yres)
        gt = ds.GetGeoTransform()

        nrows, ncols = data.shape
        cellsize = abs(gt[1])
        xll = gt[0]
        yul = gt[3]
        yll = yul - nrows * cellsize

        # Handle nodata
        nodata = band.GetNoDataValue()
        if nodata is not None:
            data[data == nodata] = np.nan

        metadata = {
            "nrows": nrows,
            "ncols": ncols,
            "xllcorner": xll,
            "yllcorner": yll,
            "cellsize": cellsize,
            "projection": ds.GetProjection(),
            "nodata": nodata,
        }

        ds = None
        return data, metadata

    def _write_geotiff(self, filepath: Path, data: np.ndarray,
                       metadata: Dict[str, Any]) -> None:
        """Write GeoTIFF format."""
        from osgeo import gdal

        nrows, ncols = data.shape
        cellsize = metadata.get("cellsize", 1.0)
        xll = metadata.get("xllcorner", 0.0)
        yll = metadata.get("yllcorner", 0.0)

        driver = gdal.GetDriverByName('GTiff')
        os.makedirs(filepath.parent, exist_ok=True)
        ds = driver.Create(str(filepath), ncols, nrows, 1, gdal.GDT_Float64)

        xul = xll
        yul = yll + nrows * cellsize
        ds.SetGeoTransform((xul, cellsize, 0, yul, 0, -cellsize))

        projection = metadata.get("projection")
        if projection:
            ds.SetProjection(projection)

        band = ds.GetRasterBand(1)
        band.SetNoDataValue(-9999)

        out_data = data.copy()
        out_data[np.isnan(out_data)] = -9999

        band.WriteArray(out_data)
        ds.FlushCache()
        ds = None

    def _read_ascii_grid(self, filepath: Path) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Read ESRI ASCII grid format."""
        metadata = {}

        with open(filepath, 'r') as f:
            # Read header (6 lines)
            for _ in range(6):
                line = f.readline().strip()
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].lower()
                    value = parts[1]

                    if key == "ncols":
                        metadata["ncols"] = int(value)
                    elif key == "nrows":
                        metadata["nrows"] = int(value)
                    elif key in ["xllcorner", "xllcenter"]:
                        metadata["xllcorner"] = float(value)
                    elif key in ["yllcorner", "yllcenter"]:
                        metadata["yllcorner"] = float(value)
                    elif key == "cellsize":
                        metadata["cellsize"] = float(value)
                    elif key == "nodata_value":
                        metadata["nodata"] = float(value)

            # Read data
            data_lines = f.readlines()

        nrows = metadata.get("nrows", 0)
        ncols = metadata.get("ncols", 0)
        nodata = metadata.get("nodata", -9999)

        data = np.zeros((nrows, ncols), dtype=np.float64)

        for i, line in enumerate(data_lines):
            if i >= nrows:
                break
            values = line.strip().split()
            for j, val in enumerate(values):
                if j >= ncols:
                    break
                data[i, j] = float(val)

        data[data == nodata] = np.nan

        return data, metadata

    def _write_ascii_grid(self, filepath: Path, data: np.ndarray,
                          metadata: Dict[str, Any]) -> None:
        """Write ESRI ASCII grid format."""
        nrows, ncols = data.shape
        cellsize = metadata.get("cellsize", 1.0)
        xll = metadata.get("xllcorner", 0.0)
        yll = metadata.get("yllcorner", 0.0)
        nodata = -9999

        os.makedirs(filepath.parent, exist_ok=True)
        with open(filepath, 'w') as f:
            f.write(f"ncols         {ncols}\n")
            f.write(f"nrows         {nrows}\n")
            f.write(f"xllcorner     {xll}\n")
            f.write(f"yllcorner     {yll}\n")
            f.write(f"cellsize      {cellsize}\n")
            f.write(f"NODATA_value  {nodata}\n")

            for i in range(nrows):
                row_str = " ".join(
                    str(nodata) if np.isnan(data[i, j]) else f"{data[i, j]:.6f}"
                    for j in range(ncols)
                )
                f.write(row_str + "\n")

    # Utility methods

    def create_constant_map(self, value: float, template_path: str) -> np.ndarray:
        """Create a constant map using another map as template."""
        _, metadata = self.read_map(template_path)
        nrows = metadata["nrows"]
        ncols = metadata["ncols"]
        return np.full((nrows, ncols), value, dtype=np.float64)

    def get_metadata(self, filepath: str) -> Dict[str, Any]:
        """Get metadata from a map file."""
        _, metadata = self.read_map(filepath)
        return metadata
