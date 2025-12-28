# Vehicle Counting UI

A PyQt6-based toolkit for vehicle counting in traffic videos with homography calibration, camera extrinsics estimation, and ROI management.

## Features

- Homography estimation between image and ground planes
- Camera extrinsics calibration via MATLAB integration
- Lane-based vehicle counting with polygon ROIs
- Bounding box annotation for object detection

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

```bash
python tools/homography-estimation-tool.py   # Calibration
python tools/counting-annotation-tool.py     # Vehicle counting
python tools/polygon-annotation-tool.py      # Polygon & rectangle annotation
```

## Documentation

See [EXPLAIN.md](EXPLAIN.md) for detailed usage instructions, workflows, and MATLAB integration.

## Requirements

- Python 3.8+
- PyQt6, OpenCV, NumPy, Rasterio

**Optional:** MATLAB Engine for Python (only needed for camera extrinsics calibration, not required for homography)
