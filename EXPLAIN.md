# Vehicle Counting UI - Detailed Documentation

This document provides comprehensive usage instructions for each tool in the toolkit.

---

## Table of Contents

1. [Homography Estimation Tool](#1-homography-estimation-tool)
2. [Video Counting Annotation Tool](#2-video-counting-annotation-tool)
3. [Polygon & Rectangle Annotation Tool](#3-polygon--rectangle-annotation-tool)
4. [MATLAB Camera Calibration](#4-matlab-camera-calibration-optional)
5. [Data Formats](#5-data-formats)

---

## 1. Homography Estimation Tool

**File:** `tools/homography-estimation-tool.py`

A dual-plane calibration tool for establishing correspondence between image plane (camera view) and ground plane (orthophoto/map).

### Purpose

- Compute homography matrix for perspective transformation
- Map pixel coordinates to real-world UTM coordinates
- Calibrate camera extrinsics using MATLAB (optional)
- Manage ROI polygons synchronized across both planes

### Launch

```bash
python tools/homography-estimation-tool.py
```

### Workflow

#### Step 1: Load Images

1. **File → Load Image Plane Image**: Load your camera image or video (`.jpg`, `.png`, `.mp4`, `.avi`)
2. **File → Load Ground Plane Image**: Load orthophoto (`.tif`, `.img`) or reference image

#### Step 2: Place Point Correspondences

1. Press `I` to enter image plane point mode
2. Click on a recognizable feature in the image plane
3. Press `G` to enter ground plane point mode
4. Click on the corresponding location in the ground plane
5. Repeat for at least 4 point pairs (more points = better accuracy)

#### Step 3: Compute Homography

1. Click **"Homography"** button
2. A popup shows the warped image overlaid on the ground plane
3. Green circles = original ground points, Red circles = reprojected points

#### Step 4: Verify and Save

1. Click **"Reproj Error"** to see RMSE in pixels
2. Press `S` or click **"Save Progress"** to save:
   - `image_points.txt` - Image plane coordinates
   - `ground_points.txt` - Ground plane coordinates
   - `homography.txt` - 3x3 homography matrix
   - `georef_points.txt` - UTM coordinates (if orthophoto loaded)

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `I` | Point annotation mode - Image plane |
| `G` | Point annotation mode - Ground plane |
| `P` | Polygon annotation mode |
| `Escape` | Exit current mode |
| `Space` | Play/pause video |
| `←` / `→` | Seek video backward/forward |
| `S` | Save progress |
| `C` | Reset all annotations |

### Buttons

| Button | Function |
|--------|----------|
| Delete Last Point - Image | Remove last point from image plane |
| Delete Last Point - Ground | Remove last point from ground plane |
| Delete Last Polygon | Remove last polygon from both planes |
| Homography | Compute homography matrix |
| Load Homography | Load existing homography from file |
| Save Progress | Save points and homography |
| Save Polygons | Save ROI polygons to JSON |
| Reproj Error | Calculate reprojection RMSE |
| Load Points | Load saved point correspondences |
| Load ROI | Load ROI polygons from JSON |
| Load Camera | Load MATLAB camera parameters |
| Calibrate | Run MATLAB camera calibration |

---

## 2. Video Counting Annotation Tool

**File:** `tools/counting-annotation-tool.py`

A video annotation tool for counting vehicles passing through defined polygon regions with lane-based classification.

### Purpose

- Count vehicles in video streams
- Track counts per polygon ROI
- Separate counts by lane (up to 3 lanes)
- Export counts with ROI definitions

### Launch

```bash
python tools/counting-annotation-tool.py
```

### Workflow

#### Step 1: Load Media

1. **File → Open Video** (`Ctrl+O`): Load video file
2. **File → Open Image** (`Ctrl+I`): Load static image (optional)

#### Step 2: Define or Load ROIs

**Option A - Load existing ROI:**
1. Click **"Load ROI"** button
2. Select JSON file with polygon definitions

**Option B - Draw new polygons:**
1. Press `Ctrl+D` or go to **Controls → Draw Polygon**
2. Click to place polygon vertices
3. Press `Escape` to finish polygon

#### Step 3: Count Vehicles

1. Press `Space` to play video
2. Click inside a polygon each time a vehicle passes through
3. Count increments automatically

#### Step 4: Lane-Based Counting

1. Select lane number (1-3) from dropdown
2. Clicks now increment both total and lane-specific count
3. Click **"Lock Lanes"** to only increment lane count (not total)

#### Step 5: Save

1. Press `Ctrl+S` or click **"Save Progress"**
2. Outputs `{filename}.json` with counts and ROI coordinates

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Space` | Play/pause video |
| `←` / `→` | Seek backward/forward 1 second |
| `Ctrl+O` | Open video |
| `Ctrl+I` | Open image |
| `Ctrl+D` | Draw polygon |
| `Ctrl+S` | Save progress |
| `Escape` | Finish polygon drawing |
| `G` | Group polygons |
| `C` | Reset all |

### Buttons

| Button | Function |
|--------|----------|
| Delete Last Polygon | Remove most recent polygon |
| Save Progress | Save counts and ROIs to JSON |
| Load ROI | Load polygon definitions |
| Reset Counts | Set all counts to zero |
| Lock Lanes | Toggle lane-only counting |
| Delete Last Count P# | Decrement count for polygon # |

---

## 3. Polygon & Rectangle Annotation Tool

**File:** `tools/polygon-annotation-tool.py`

An annotation tool for creating object detection and segmentation datasets with both rectangular and polygon ROIs on images or videos.

### Purpose

- Draw rectangular bounding boxes on images/videos
- Draw polygon regions for segmentation
- Video playback with frame navigation
- Export coordinates for training

### Launch

```bash
python tools/polygon-annotation-tool.py
```

### Workflow

#### Load Media
1. **File → Open Image** (`Ctrl+I`): Open image to annotate
2. **File → Open Video** (`Ctrl+O`): Open video to annotate

#### Rectangle Annotation
1. Press `R` or **Tools → Rectangle**: Enter rectangle mode
2. Click top-left corner of object
3. Click bottom-right corner of object
4. Press `Escape` to finish

#### Polygon Annotation
1. Press `P` or **Tools → Polygon**: Enter polygon mode
2. Click to place vertices
3. Press `Escape` to close polygon

#### Video Playback
1. Press `Space` to play/pause
2. Use `←` / `→` to seek backward/forward
3. Use slider to jump to position

4. Click **"Save Progress"** or press `S` to export

### Output

Saves to `roi.json`:
```json
{
  "rectangles": {
    "0": [x1, y1, x2, y2],
    "1": [x1, y1, x2, y2]
  },
  "polygons": {
    "0": [[x1, y1], [x2, y2], [x3, y3]],
    "1": [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
  }
}
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `R` | Rectangle mode |
| `P` | Polygon mode |
| `Escape` | Finish current annotation |
| `S` | Save progress |
| `Ctrl+I` | Open image |
| `Ctrl+O` | Open video |
| `Space` | Play/pause video |
| `←` / `→` | Seek video backward/forward |

---

## 4. MATLAB Camera Calibration (Optional)

The homography estimation tool optionally supports camera extrinsics calibration using MATLAB's Computer Vision Toolbox.

> **Note:** MATLAB is **not required** for basic functionality. You can compute homography, reproject points, and manage ROIs without MATLAB. MATLAB is only needed if you want to estimate full camera extrinsics (K, R, t matrices).

### Prerequisites

1. **MATLAB** with Computer Vision Toolbox installed
2. **MATLAB Engine for Python**:
   ```bash
   cd /path/to/matlab/extern/engines/python
   python setup.py install
   ```
3. **Camera intrinsics file** (`.mat`) from MATLAB's Camera Calibrator app

### How It Works

The tool uses MATLAB to estimate camera pose (rotation R and translation t) from 2D-3D point correspondences:

1. **2D Points**: Image plane coordinates (pixels)
2. **3D Points**: Ground plane UTM coordinates with elevation

MATLAB's `estworldpose` function computes the camera extrinsics using:
- Undistorted image points
- World coordinates (UTM + elevation)
- Camera intrinsics (focal length, principal point, distortion)

### Calibration Workflow

#### Step 1: Prepare Camera Intrinsics

In MATLAB:
```matlab
% Use Camera Calibrator app to calibrate camera
% Save cameraParams to .mat file
save('camera_params.mat', 'cameraParams');
```

#### Step 2: Load Orthophoto with Elevation

1. Load a GeoTIFF orthophoto (`.tif`) as ground plane
2. The orthophoto must have:
   - RGB bands (1-3)
   - Elevation band (band 5) - Digital Surface Model (DSM)
   - Georeferencing (UTM transform)

#### Step 3: Place Correspondences

1. Place at least 6 point correspondences
2. Points automatically capture UTM coordinates and elevation

#### Step 4: Load Camera Parameters

1. Click **"Load Camera"** button
2. Select your `camera_params.mat` file

#### Step 5: Calibrate

1. Click **"Calibrate"** button
2. MATLAB computes camera pose using RANSAC-based estimation
3. Outputs saved to `{video_name}/`:
   - `K.txt` - Camera intrinsic matrix (3x3)
   - `R.txt` - Rotation matrix (3x3)
   - `t.txt` - Translation vector (3x1)

### Output Files

**K.txt** - Intrinsic Matrix:
```
fx  0   cx
0   fy  cy
0   0   1
```

**R.txt** - Rotation Matrix (world to camera):
```
r11 r12 r13
r21 r22 r23
r31 r32 r33
```

**t.txt** - Translation Vector (camera position in world):
```
tx
ty
tz
```

### Usage in Computer Vision

The camera matrix P = K[R|t] can project 3D world points to 2D image:
```python
import numpy as np

K = np.loadtxt('K.txt')
R = np.loadtxt('R.txt')
t = np.loadtxt('t.txt')

# Projection matrix
P = K @ np.hstack((R, t))

# Project 3D point to 2D
world_point = np.array([utm_x, utm_y, elevation, 1])
image_point = P @ world_point
image_point = image_point[:2] / image_point[2]
```

---

## 5. Data Formats

### ROI JSON Format

```json
{
  "1": {
    "roi": [[0.1, 0.2], [0.3, 0.2], [0.3, 0.4], [0.1, 0.4]],
    "counts": 42,
    "lanes": {"1": 15, "2": 18, "3": 9}
  },
  "2": {
    "roi": [[0.5, 0.5], [0.7, 0.5], [0.7, 0.7], [0.5, 0.7]],
    "counts": 28,
    "lanes": {"1": 10, "2": 12, "3": 6}
  },
  "group": {
    "entry": [1, 2],
    "exit": [3, 4]
  }
}
```

- **roi**: Normalized polygon vertices (0-1 range)
- **counts**: Total vehicle count
- **lanes**: Per-lane counts
- **group**: Polygon groupings (e.g., entry/exit zones)

### Point Files

**image_points.txt** / **ground_points.txt**:
```
x1 y1
x2 y2
x3 y3
```

**georef_points.txt** (UTM + elevation):
```
utm_x1 utm_y1 elevation1
utm_x2 utm_y2 elevation2
utm_x3 utm_y3 elevation3
```

### Homography Matrix

**homography.txt**:
```
h11 h12 h13
h21 h22 h23
h31 h32 h33
```

Transform image point to ground: `[x', y', w]^T = H * [x, y, 1]^T`

---

## Tips

1. **Point Placement**: Use distinctive features visible in both planes (corners, road markings)
2. **Minimum Points**: 4 for homography, 6+ recommended for better accuracy
3. **Video Navigation**: Use `←`/`→` for frame-by-frame counting
4. **Zoom**: Right-click drag to zoom into region, double-right-click to reset
5. **UTM Coordinates**: Only available with georeferenced orthophotos (`.tif` with transform)
