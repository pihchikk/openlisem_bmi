"""
Map I/O utilities for OpenLISEM BMI wrapper.

Handles reading and writing of spatial data in various formats:
- PCRaster map format (.map)
- GeoTIFF format (.tif, .tiff)
- ASCII grid format (.asc)
"""

import os
import struct
import numpy as np
from typing import Tuple, Dict, Optional, Any
from pathlib import Path


class MapIO:
    """
    Map I/O handler for OpenLISEM spatial data.

    Supports multiple file formats used by OpenLISEM:
    - PCRaster binary maps
    - GeoTIFF (via GDAL if available)
    - ASCII grid format
    """

    def __init__(self, base_dir: str = "."):
        """
        Initialize the map I/O handler.

        Parameters
        ----------
        base_dir : str
            Base directory for relative paths
        """
        self.base_dir = base_dir
        self._gdal_available = self._check_gdal()

    def _check_gdal(self) -> bool:
        """Check if GDAL is available."""
        try:
            from osgeo import gdal
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

        if ext == ".map":
            return self._read_pcraster(filepath)
        elif ext in [".tif", ".tiff"]:
            return self._read_geotiff(filepath)
        elif ext == ".asc":
            return self._read_ascii_grid(filepath)
        else:
            # Try GDAL for unknown formats
            if self._gdal_available:
                return self._read_geotiff(filepath)
            else:
                raise ValueError(f"Unsupported file format: {ext}")

    def write_map(self, filepath: str, data: np.ndarray,
                  metadata: Dict[str, Any], format: str = "auto") -> None:
        """
        Write a map file.

        Parameters
        ----------
        filepath : str
            Output path
        data : np.ndarray
            2D array of values
        metadata : dict
            Metadata including cellsize, origin, etc.
        format : str
            Output format ('pcraster', 'geotiff', 'ascii', or 'auto')
        """
        filepath = Path(filepath)

        if format == "auto":
            ext = filepath.suffix.lower()
            if ext == ".map":
                format = "pcraster"
            elif ext in [".tif", ".tiff"]:
                format = "geotiff"
            elif ext == ".asc":
                format = "ascii"
            else:
                format = "pcraster"

        if format == "pcraster":
            self._write_pcraster(filepath, data, metadata)
        elif format == "geotiff":
            self._write_geotiff(filepath, data, metadata)
        elif format == "ascii":
            self._write_ascii_grid(filepath, data, metadata)
        else:
            raise ValueError(f"Unknown output format: {format}")

    # PCRaster format support

    def _read_pcraster(self, filepath: Path) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Read PCRaster format map."""
        metadata = {}

        with open(filepath, 'rb') as f:
            # Read PCRaster header
            # PCRaster uses a 64-byte header
            header = f.read(64)

            # Parse header (simplified - assumes scalar float)
            # Signature should be at bytes 0-1
            signature = struct.unpack('<H', header[0:2])[0]

            # Version at byte 2
            version = header[2]

            # Value scale at bytes 3-4
            value_scale = struct.unpack('<H', header[3:5])[0]

            # Cell representation at byte 5
            cell_repr = header[5]

            # Projection at bytes 6-7
            projection = struct.unpack('<H', header[6:8])[0]

            # Get dimensions from bytes 8-15
            nrows = struct.unpack('<I', header[8:12])[0]
            ncols = struct.unpack('<I', header[12:16])[0]

            # Get extent information (bytes 16-48)
            xul = struct.unpack('<d', header[16:24])[0]
            yul = struct.unpack('<d', header[24:32])[0]
            cellsize = struct.unpack('<d', header[32:40])[0]

            # Angle at bytes 40-48
            angle = struct.unpack('<d', header[40:48])[0]

            metadata = {
                "nrows": nrows,
                "ncols": ncols,
                "xllcorner": xul,
                "yllcorner": yul - nrows * cellsize,  # Convert to lower-left
                "cellsize": cellsize,
                "angle": angle,
                "projection": projection,
                "value_scale": value_scale,
            }

            # Read data
            # PCRaster scalar float is 4 bytes per cell
            data_size = nrows * ncols * 4
            raw_data = f.read(data_size)

            # Unpack as float32
            data = np.frombuffer(raw_data, dtype=np.float32).reshape(nrows, ncols)

            # Handle missing values (PCRaster uses 1e31 as MV)
            mv_mask = np.abs(data) > 1e30
            data = data.astype(np.float64)
            data[mv_mask] = np.nan

        return data, metadata

    def _write_pcraster(self, filepath: Path, data: np.ndarray,
                        metadata: Dict[str, Any]) -> None:
        """Write PCRaster format map."""
        nrows, ncols = data.shape
        cellsize = metadata.get("cellsize", 1.0)
        xll = metadata.get("xllcorner", 0.0)
        yll = metadata.get("yllcorner", 0.0)
        xul = xll
        yul = yll + nrows * cellsize

        # Create header (64 bytes)
        header = bytearray(64)

        # Signature (0x0035 or 0x5300 for Intel byte order)
        struct.pack_into('<H', header, 0, 0x0035)

        # Version
        header[2] = 2

        # Value scale (1 = VS_BOOLEAN, 2 = VS_NOMINAL, 3 = VS_ORDINAL,
        #              4 = VS_SCALAR, 5 = VS_DIRECTION, 6 = VS_LDD)
        struct.pack_into('<H', header, 3, 4)  # VS_SCALAR

        # Cell representation (0xD4 = CR_REAL4, single precision float)
        header[5] = 0xD4

        # Projection (0 = PT_YDECT2B, y increases from top to bottom)
        struct.pack_into('<H', header, 6, 0)

        # Dimensions
        struct.pack_into('<I', header, 8, nrows)
        struct.pack_into('<I', header, 12, ncols)

        # Extent
        struct.pack_into('<d', header, 16, xul)
        struct.pack_into('<d', header, 24, yul)
        struct.pack_into('<d', header, 32, cellsize)

        # Angle
        struct.pack_into('<d', header, 40, 0.0)

        # Convert data
        out_data = data.astype(np.float32)

        # Replace NaN with PCRaster missing value
        out_data[np.isnan(out_data)] = 1e31

        # Write file
        os.makedirs(filepath.parent, exist_ok=True)
        with open(filepath, 'wb') as f:
            f.write(header)
            f.write(out_data.tobytes())

    # GeoTIFF format support

    def _read_geotiff(self, filepath: Path) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Read GeoTIFF format map."""
        if not self._gdal_available:
            raise ImportError("GDAL is required to read GeoTIFF files")

        from osgeo import gdal

        ds = gdal.Open(str(filepath))
        if ds is None:
            raise IOError(f"Could not open GeoTIFF: {filepath}")

        band = ds.GetRasterBand(1)
        data = band.ReadAsArray().astype(np.float64)

        # Get geotransform
        gt = ds.GetGeoTransform()
        # gt = (xmin, xres, 0, ymax, 0, -yres)

        nrows, ncols = data.shape
        cellsize = gt[1]
        xll = gt[0]
        yul = gt[3]
        yll = yul - nrows * abs(gt[5])

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
        }

        ds = None
        return data, metadata

    def _write_geotiff(self, filepath: Path, data: np.ndarray,
                       metadata: Dict[str, Any]) -> None:
        """Write GeoTIFF format map."""
        if not self._gdal_available:
            raise ImportError("GDAL is required to write GeoTIFF files")

        from osgeo import gdal

        nrows, ncols = data.shape
        cellsize = metadata.get("cellsize", 1.0)
        xll = metadata.get("xllcorner", 0.0)
        yll = metadata.get("yllcorner", 0.0)

        driver = gdal.GetDriverByName('GTiff')
        os.makedirs(filepath.parent, exist_ok=True)
        ds = driver.Create(str(filepath), ncols, nrows, 1, gdal.GDT_Float64)

        # Set geotransform
        xul = xll
        yul = yll + nrows * cellsize
        ds.SetGeoTransform((xul, cellsize, 0, yul, 0, -cellsize))

        # Set projection if available
        projection = metadata.get("projection")
        if projection:
            ds.SetProjection(projection)

        # Write data
        band = ds.GetRasterBand(1)
        band.SetNoDataValue(-9999)

        out_data = data.copy()
        out_data[np.isnan(out_data)] = -9999

        band.WriteArray(out_data)
        ds.FlushCache()
        ds = None

    # ASCII grid format support

    def _read_ascii_grid(self, filepath: Path) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Read ESRI ASCII grid format."""
        metadata = {}

        with open(filepath, 'r') as f:
            # Read header
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
                    elif key == "xllcorner" or key == "xllcenter":
                        metadata["xllcorner"] = float(value)
                    elif key == "yllcorner" or key == "yllcenter":
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

        # Replace nodata with NaN
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
        """
        Create a constant map using another map as template.

        Parameters
        ----------
        value : float
            Constant value to fill
        template_path : str
            Path to template map

        Returns
        -------
        np.ndarray
            Array filled with constant value
        """
        _, metadata = self.read_map(template_path)
        nrows = metadata["nrows"]
        ncols = metadata["ncols"]

        return np.full((nrows, ncols), value, dtype=np.float64)

    def create_empty_map(self, template_path: str, fill_value: float = 0.0) -> np.ndarray:
        """
        Create an empty map using another map as template.

        Parameters
        ----------
        template_path : str
            Path to template map
        fill_value : float
            Value to fill the map with

        Returns
        -------
        np.ndarray
            Empty array with same shape as template
        """
        return self.create_constant_map(fill_value, template_path)

    def get_metadata(self, filepath: str) -> Dict[str, Any]:
        """
        Get metadata from a map file without loading data.

        Parameters
        ----------
        filepath : str
            Path to map file

        Returns
        -------
        dict
            Metadata dictionary
        """
        _, metadata = self.read_map(filepath)
        return metadata

    def resample_map(self, data: np.ndarray, source_meta: Dict[str, Any],
                     target_meta: Dict[str, Any]) -> np.ndarray:
        """
        Resample a map to a different grid.

        Parameters
        ----------
        data : np.ndarray
            Source data array
        source_meta : dict
            Source map metadata
        target_meta : dict
            Target map metadata

        Returns
        -------
        np.ndarray
            Resampled data array
        """
        from scipy import ndimage

        src_rows, src_cols = data.shape
        tgt_rows = target_meta["nrows"]
        tgt_cols = target_meta["ncols"]

        # Calculate zoom factors
        zoom_row = tgt_rows / src_rows
        zoom_col = tgt_cols / src_cols

        # Resample using nearest neighbor
        resampled = ndimage.zoom(data, (zoom_row, zoom_col), order=0)

        return resampled
