# Vehicle Counting UI

A comprehensive PyQt6-based annotation and analysis platform for vehicle counting in videos with advanced computer vision capabilities including perspective correction, ground-plane calibration, and multi-lane tracking.

## Overview

This toolkit provides multiple specialized applications for traffic monitoring and analysis:

- **Video Counting Annotation**: Interactive vehicle counting with polygon ROIs and multi-lane tracking
- **Homography Estimation Tool**: Dual-plane annotation with perspective transformation and ground-plane calibration
- **Rectangle Annotation GUI**: Simple bounding box annotation for static images
- **Google Maps Downloader**: Utility for downloading high-resolution reference imagery

## Features

### Core Capabilities
- ✅ Video playback with frame-by-frame control
- ✅ Interactive polygon and rectangle drawing
- ✅ Multi-lane vehicle counting (configurable up to 3 lanes)
- ✅ Click-to-count interface with lane-specific tracking
- ✅ Perspective correction via homography transformation
- ✅ Dual-plane annotation (camera view ↔ bird's-eye ground plane)
- ✅ Synchronized annotations across multiple views
- ✅ Geospatial support with UTM coordinates
- ✅ GeoTIFF/orthophoto integration
- ✅ Zoom/pan interface with mouse controls
- ✅ Persistent configurations via JSON
- ✅ Polygon grouping (entrance/exit zones)

### Advanced Features
- Homography matrix computation and display
- Reprojection between camera and ground perspectives
- MATLAB engine integration for advanced calibration
- Dynamic video scaling based on resolution
- Google Maps tile downloading and stitching

## Installation

### Requirements
- Python 3.8+
- PyQt6 or PyQt5
- OpenCV
- NumPy
- MATLAB Engine (optional, for advanced calibration)

### Setup

```bash
# Clone the repository
git clone <repository-url>
cd vehicle_counting_ui

# Install dependencies
pip install -r requirements.txt
```

### Dependencies
```
PyQt6==6.7.0
PyQt6-Qt6==6.7.0
PyQt6-sip==13.6.0
numpy==1.24.4
opencv-python==4.8.0.74
Pillow==10.4.0
rasterio (for GeoTIFF support)
requests==2.28.0 (for Google Maps downloader)
```

## Usage

### 1. Video Counting Annotation (Main Application)

Launch the main vehicle counting interface:

```bash
python video_counting_annotation.py
```

**Workflow:**
1. **Load Video**: File → Open Video
2. **Draw ROI**: Press `Ctrl+D` to enter drawing mode, click to add polygon points
3. **Count Vehicles**: Click inside polygon to increment counter
4. **Select Lane**: Use dropdown to track different lanes (1, 2, or 3)
5. **Save ROI**: File → Save ROI to export configuration as JSON
6. **Load ROI**: File → Load ROI to import existing configuration

**Keyboard Shortcuts:**
- `Space`: Play/Pause video
- `Left/Right Arrow`: Navigate frames
- `Ctrl+D`: Toggle drawing mode
- `G`: Group polygons (entrance/exit)
- `Delete`: Remove selected polygon

**Features:**
- Multi-lane counting with per-lane statistics
- Persistent ROI configurations
- Draggable polygon points (green circles)
- Real-time counter display on polygons

### 2. Homography Estimation Tool

Launch the dual-plane calibration tool:

```bash
python homography_estimation_tool.py
```

**Workflow:**
1. **Load Image/Video**: Load camera view in image plane
2. **Load Ground Reference**: Load orthophoto or map in ground plane
3. **Add Points**: Click to add corresponding points in both planes
4. **Compute Homography**: Tool automatically calculates transformation
5. **Annotate**: Draw polygons that sync across both planes
6. **Reproject**: Points and polygons automatically transform between views

**Use Cases:**
- Camera calibration for traffic monitoring
- Perspective correction for bird's-eye view generation
- Ground truth annotation with georeferencing
- UTM coordinate conversion

**Supported Formats:**
- Images: JPEG, PNG, BMP
- Videos: MP4, AVI, MOV
- Geospatial: GeoTIFF with UTM coordinates

### 3. Rectangle Annotation GUI

Launch the bounding box annotation tool:

```bash
python rectangle_annotation_gui.py
```

**Workflow:**
1. Load image
2. Click to define rectangle corners
3. View coordinates and dimensions
4. Save annotations to JSON

### 4. Google Maps Downloader

Download high-resolution map tiles:

```bash
python gmaps_downloader.py
```

**Usage Example:**
```python
from gmaps_downloader import GoogleMapDownloader, GoogleMapsLayers

# Download satellite imagery
gmd = GoogleMapDownloader(37.7749, -122.4194, 15, GoogleMapsLayers.SATELLITE)
img = gmd.generateImage()
img.save("output.png")
```

## Data Format

### ROI JSON Structure

Annotations are saved with normalized coordinates (0.0 to 1.0):

```json
{
  "1": {
    "roi": [[0.25, 0.30], [0.35, 0.30], [0.35, 0.45], [0.25, 0.45]],
    "counts": 42,
    "lanes": {
      "1": 15,
      "2": 20,
      "3": 7
    }
  },
  "2": {
    "roi": [[0.50, 0.40], [0.60, 0.40], [0.60, 0.55], [0.50, 0.55]],
    "counts": 28,
    "lanes": {
      "1": 10,
      "2": 12,
      "3": 6
    }
  },
  "group": {
    "entrance": [0, 1],
    "exit": [2, 3]
  }
}
```

**Fields:**
- `roi`: Array of [x, y] coordinates (normalized 0-1)
- `counts`: Total vehicle count for this ROI
- `lanes`: Per-lane count breakdown
- `group`: Optional grouping of ROIs (entrance/exit zones)

## Architecture

### Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| GUI Framework | PyQt6 | Main interface and widgets |
| Computer Vision | OpenCV 4.8.0 | Homography, transformations |
| Numerical Computing | NumPy 1.24.4 | Matrix operations |
| Geospatial | Rasterio | GeoTIFF/orthophoto support |
| Image Processing | Pillow 10.4.0 | Format conversions |
| Calibration | MATLAB Engine | Advanced calibration (optional) |

### Design Pattern

The application follows the Qt Model-View architecture:

```
Scene (QGraphicsScene)
  ├── Data storage and logic
  ├── Coordinate transformations
  └── Annotation persistence
      ↓
Items (QGraphicsItem)
  ├── PolygonAnnotation
  ├── PointAnnotation
  └── GripItem (control points)
      ↓
View (QGraphicsView)
  ├── Rendering and viewport
  └── Zoom/pan controls
      ↓
Window (QMainWindow)
  └── Menus and controls
```

### Key Classes

**Video Counting Annotation:**
- `PolygonAnnotation`: ROI polygon with counter and lane tracking
- `GripItem`: Draggable control point (green/red circles)
- `AnnotationScene`: Manages polygons, video playback, persistence
- `QtPolygonViewer`: Graphics view with zoom/pan
- `VideoCountingAnnotation`: Main window with controls

**Homography Estimation:**
- `PointAnnotation`: Calibration points with UTM support
- `PolygonAnnotation`: Synchronized polygon across planes
- `HomographyScene`: Dual-plane scene with transformation logic
- `AnnotationWindow`: Split-view interface

## File Structure

```
vehicle_counting_ui/
├── video_counting_annotation.py    # Main application (760 lines)
├── homography_estimation_tool.py   # Calibration tool (1,311 lines)
├── rectangle_annotation_gui.py     # Rectangle tool (339 lines)
├── polygon_annotation.py           # Legacy polygon tool (211 lines)
├── QtImageViewer.py                # Image viewer utility (200 lines)
├── gmaps_downloader.py             # Maps downloader (131 lines)
├── requirements.txt                # Python dependencies
└── README.md                       # This file
```

## Use Cases

1. **Traffic Monitoring**: Count vehicles on roads with lane-specific tracking
2. **Parking Analysis**: Track parking lot utilization over time
3. **Urban Planning**: Analyze traffic patterns from aerial/ground perspectives
4. **Autonomous Driving**: Generate training data with perspective-aware annotations
5. **Event Analytics**: Monitor vehicle flow at events or checkpoints
6. **Research**: Computer vision research on perspective transformation

## Development

### Recent Changes

- **Dynamic Scaling**: Added video resolution-based scaling for better display
- **Homography Correction**: Improved perspective transformation accuracy
- **ROI Management**: Enhanced ROI editing on both image and ground planes
- **Reprojection**: Bidirectional reprojection between camera and ground views
- **Orthophoto Calibration**: MATLAB engine integration for advanced calibration

### Contributing

This is a research/production tool for traffic analysis. Contributions should focus on:
- Improved calibration algorithms
- Additional annotation types
- Performance optimizations
- Export format support
- Documentation improvements

## License

[Add license information]

## Contact

[Add contact information]

## Acknowledgments

Built with PyQt6, OpenCV, and NumPy for computer vision and traffic analysis research.
