"""
Homography Estimation Tool for image-to-ground plane calibration.

A PyQt6-based GUI tool for establishing correspondence between image plane
and ground plane using homography matrix computation. Supports orthophoto
overlays, UTM coordinates, and optional MATLAB camera calibration.
"""

import json
import os
import sys
from collections import defaultdict
from enum import Enum
from functools import partial

import cv2
import numpy as np
import rasterio
from PyQt6 import QtWidgets, QtGui, QtCore, QtMultimedia, QtMultimediaWidgets
from PyQt6.QtCore import pyqtSignal, Qt, QSizeF, QUrl
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget, QMessageBox

# Optional MATLAB engine for camera calibration
try:
    import matlab.engine
    MATLAB_ENGINE = matlab.engine.start_matlab()
except ImportError:
    MATLAB_ENGINE = None
    print('MATLAB engine not installed. Camera calibration disabled.')


class Instructions(Enum):
    """Annotation mode instructions."""
    NO_INSTRUCTION = 0
    POINT = 1
    POLYGON = 2


def convert_cv_to_qt(cv_img: np.ndarray, is_rgb: bool = False) -> QtGui.QPixmap:
    """
    Convert OpenCV image to Qt pixmap.

    Args:
        cv_img: OpenCV image array (BGR or RGB).
        is_rgb: True if image is already RGB format.

    Returns:
        QPixmap for display in Qt widgets.
    """
    if not is_rgb:
        cv_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)

    h, w, ch = cv_img.shape
    bytes_per_line = ch * w
    q_img = QtGui.QImage(cv_img.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
    return QtGui.QPixmap.fromImage(q_img)


def pixel_to_utm(pixel: tuple, transform: rasterio.Affine) -> tuple:
    """
    Convert pixel coordinates to UTM using rasterio transform.

    Args:
        pixel: (x, y) pixel coordinates.
        transform: Rasterio affine transform matrix.

    Returns:
        (utm_x, utm_y) coordinates.
    """
    return rasterio.transform.xy(transform, pixel[1], pixel[0])


class GripItem(QtWidgets.QGraphicsPathItem):
    """
    Draggable control point for annotations.

    Provides visual feedback on hover and synchronizes positions
    between image and ground plane views.
    """

    _circle = QtGui.QPainterPath()
    _circle.addEllipse(QtCore.QRectF(-10, -10, 20, 20))
    _square = QtGui.QPainterPath()
    _square.addRect(QtCore.QRectF(-15, -15, 30, 30))

    def __init__(self, annotation: 'PointAnnotation | PolygonAnnotation',
                 index: int = 0, polygon_id: int = 0):
        """
        Initialize grip item.

        Args:
            annotation: Parent annotation item.
            index: Point index within annotation.
            polygon_id: ID of parent polygon (for polygon synchronization).
        """
        super().__init__()
        self._annotation = annotation
        self._index = index
        self._polygon_id = polygon_id

        self.setPath(self._circle)
        self.setBrush(QtGui.QColor("green"))
        self.setPen(QtGui.QPen(QtGui.QColor("green"), 2))
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(11)
        self.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))

    def hoverEnterEvent(self, event):
        """Highlight on hover."""
        self.setPath(self._square)
        self.setBrush(QtGui.QColor("red"))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Reset appearance on hover exit."""
        self.setPath(self._circle)
        self.setBrush(QtGui.QColor("green"))
        super().hoverLeaveEvent(event)

    def mouseReleaseEvent(self, event):
        """Deselect on mouse release."""
        self.setSelected(False)
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        """Synchronize position changes across planes."""
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.isEnabled():
            self._annotation.movePoint(self._index, value)

            # Synchronize polygon points between planes
            if isinstance(self._annotation, PolygonAnnotation):
                self._syncPolygonAcrossPlanes(value)

        return super().itemChange(change, value)

    def _syncPolygonAcrossPlanes(self, value):
        """Synchronize polygon point movement to other plane."""
        scene = self._annotation._scene
        viewer = scene._viewer

        if viewer.homography_matrix is None:
            return

        pos = scene.toNumpy(value)

        if scene._is_ground_plane:
            # Ground -> Image plane
            reproj = viewer.reprojectToImage(pos)
            target_scene = viewer._image_plane.scene
        else:
            # Image -> Ground plane
            reproj = viewer.reprojectToGround(pos)
            target_scene = viewer._ground_plane.scene

        target_pos = scene.toQPointF(reproj[0])
        if self._polygon_id in target_scene._polygon_items:
            polygon = target_scene._polygon_items[self._polygon_id]
            polygon.movePoint(self._index, target_pos)
            polygon.setGripPosition(self._index, target_pos)


class PointAnnotation(QtWidgets.QGraphicsItem):
    """Single point annotation with coordinate display."""

    def __init__(self, parent=None):
        """Initialize point annotation."""
        super().__init__()
        self.setZValue(10)
        self.setAcceptHoverEvents(True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))

        self._grip = None
        self._utm_coords = None

        # Coordinate label
        self._label = QtWidgets.QGraphicsTextItem('', self)
        self._label.setDefaultTextColor(QtGui.QColor(0, 255, 0))
        self._label.setFont(QtGui.QFont('Arial', 10, QtGui.QFont.Weight.Bold))

    def boundingRect(self):
        """Return bounding rectangle."""
        return QtCore.QRectF()

    def paint(self, painter, option, widget):
        """Paint method (no-op for container item)."""
        pass

    @property
    def position(self) -> tuple:
        """Return (x, y) position."""
        return (self._grip.x(), self._grip.y()) if self._grip else (0, 0)

    @property
    def utm_position(self) -> list:
        """Return UTM coordinates if available."""
        return self._utm_coords or []

    def setPoint(self, pos: QtCore.QPointF, point_id: int):
        """Set point position and ID."""
        local_pos = self.mapFromScene(pos)
        self._grip = GripItem(self, point_id)
        self.scene().addItem(self._grip)
        self._grip.setPos(local_pos)
        self._label.setPlainText(f'ID: {point_id}')
        self._label.setPos(local_pos)

    def movePoint(self, point_id: int, pos: QtCore.QPointF):
        """Move point to new position."""
        local_pos = self.mapFromScene(pos)
        self._grip.setPos(local_pos)
        self._label.setPos(local_pos)
        self._label.setPlainText(f'ID: {point_id}')


class PolygonAnnotation(QtWidgets.QGraphicsPolygonItem):
    """Interactive polygon annotation with synchronized plane updates."""

    def __init__(self, scene: 'HomographyScene', parent=None):
        """
        Initialize polygon annotation.

        Args:
            scene: Parent HomographyScene.
            parent: Parent graphics item.
        """
        super().__init__(parent)
        self._scene = scene
        self._points = []
        self._grips = []
        self.label = 0

        self.setZValue(10)
        self.setPen(QtGui.QPen(QtGui.QColor("green"), 2))
        self.setAcceptHoverEvents(True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))

        # ID label
        self._id_label = QtWidgets.QGraphicsTextItem('', self)
        self._id_label.setDefaultTextColor(QtGui.QColor(0, 255, 0))
        self._id_label.setFont(QtGui.QFont('Arial', 20, QtGui.QFont.Weight.Bold))

    @property
    def num_points(self) -> int:
        """Return number of vertices."""
        return len(self._grips)

    @property
    def vertices(self) -> np.ndarray:
        """Return vertices as numpy array."""
        return np.array([[p.x(), p.y()] for p in self._points])

    @property
    def centroid(self) -> np.ndarray:
        """Return polygon centroid."""
        if not self._points:
            return np.array([0, 0])
        return self.vertices.mean(axis=0)

    def addPoint(self, pos: QtCore.QPointF):
        """Add vertex to polygon."""
        self._points.append(pos)
        self.setPolygon(QtGui.QPolygonF(self._points))

        grip = GripItem(self, len(self._points) - 1, polygon_id=self.label)
        self.scene().addItem(grip)
        self._grips.append(grip)
        grip.setPos(pos)

    def removeLastPoint(self):
        """Remove last vertex."""
        if self._points:
            self._points.pop()
            self.setPolygon(QtGui.QPolygonF(self._points))
            grip = self._grips.pop()
            self.scene().removeItem(grip)

    def movePoint(self, index: int, pos: QtCore.QPointF):
        """Move vertex to new position."""
        if 0 <= index < len(self._points):
            self._points[index] = self.mapFromScene(pos)
            self.setPolygon(QtGui.QPolygonF(self._points))
            self._updateLabel()

    def setGripPosition(self, index: int, pos: QtCore.QPointF):
        """Set grip position without triggering change events."""
        if 0 <= index < len(self._grips):
            self._grips[index].setPos(pos)

    def _updateLabel(self):
        """Update label position to centroid."""
        center = self.centroid
        self._id_label.setPos(QtCore.QPointF(center[0], center[1]))
        self._id_label.setPlainText(str(self.label + 1))

    def _syncGrips(self):
        """Synchronize grip positions after polygon movement."""
        for i, point in enumerate(self._points):
            if i < len(self._grips):
                grip = self._grips[i]
                grip.setEnabled(False)
                grip.setPos(self.mapToScene(point))
                grip.setEnabled(True)

    def itemChange(self, change, value):
        """Handle polygon movement."""
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._syncGrips()
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        """Highlight on hover."""
        self.setBrush(QtGui.QColor(255, 0, 0, 100))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Reset appearance on hover exit."""
        self.setBrush(QtGui.QBrush(Qt.BrushStyle.NoBrush))
        super().hoverLeaveEvent(event)


class HomographyScene(QtWidgets.QGraphicsScene):
    """Graphics scene for homography calibration with image/video support."""

    def __init__(self, viewer: 'HomographyViewer', is_ground_plane: bool = False,
                 show_utm: bool = False):
        """
        Initialize scene.

        Args:
            viewer: Parent HomographyViewer widget.
            is_ground_plane: True if this is the ground plane scene.
            show_utm: True to display UTM coordinates.
        """
        super().__init__(viewer)
        self._viewer = viewer
        self._is_ground_plane = is_ground_plane
        self._show_utm = show_utm
        self._file_loaded = False
        self._reset()

    def _reset(self):
        """Reset scene to initial state."""
        # Image display
        self._image_item = QtWidgets.QGraphicsPixmapItem()
        self._image_item.setCursor(QtGui.QCursor(Qt.CursorShape.CrossCursor))

        # Video player
        self._player = QtMultimedia.QMediaPlayer()
        self._video_item = QtMultimediaWidgets.QGraphicsVideoItem()
        self._video_item.setCursor(QtGui.QCursor(Qt.CursorShape.CrossCursor))
        self._video_item.setSize(QSizeF(3840, 2160))
        self._video_item.nativeSizeChanged.connect(self._onVideoSizeChanged)
        self._player.setVideoOutput(self._video_item)

        # Annotations
        self._current_point = None
        self._current_polygon = None
        self._point_items = {}
        self._polygon_items = {}
        self._point_count = 0
        self._polygon_count = 0

        # State
        self._instruction = Instructions.NO_INSTRUCTION
        self._media_type = None
        self._filename = None
        self._width = None
        self._height = None

        # Orthophoto data
        self._orthophoto = None
        self._transform = None
        self._elevation_map = None
        self._has_utm = False

        # Coordinate display
        self._coord_label = None
        self._roi_data = None

    def _onVideoSizeChanged(self, size: QSizeF):
        """Handle video native size change."""
        self._video_item.setSize(size)
        self.setSceneRect(self._video_item.boundingRect())

    @property
    def player(self) -> QtMultimedia.QMediaPlayer:
        """Return video player."""
        return self._player

    def loadImage(self, filename: str):
        """
        Load image or video file.

        Args:
            filename: Path to image/video file.
        """
        ext = os.path.splitext(filename)[1].lower()

        if self._is_ground_plane and ext in ('.tif', '.img'):
            # Load orthophoto with geospatial data
            self._orthophoto = rasterio.open(filename)
            r, g, b = self._orthophoto.read(1), self._orthophoto.read(2), self._orthophoto.read(3)
            cv_img = np.dstack((r, g, b))

            if self._orthophoto.count > 4:
                self._elevation_map = self._orthophoto.read(5)

            self._image_item.setPixmap(convert_cv_to_qt(cv_img, is_rgb=True))
            self._transform = self._orthophoto.transform
            self._has_utm = self._show_utm
            self.addItem(self._image_item)
            self.setSceneRect(self._image_item.boundingRect())
            self._media_type = 'image'

        elif ext in ('.jpg', '.png', '.bmp'):
            self._image_item.setPixmap(QtGui.QPixmap(filename))
            self.addItem(self._image_item)
            self.setSceneRect(self._image_item.boundingRect())
            self._media_type = 'image'

        elif ext in ('.mp4', '.avi'):
            self._player.setSource(QUrl.fromLocalFile(filename))
            self.addItem(self._video_item)
            self.setSceneRect(self._video_item.boundingRect())
            self._media_type = 'video'

        self._filename = filename
        self._width = self.width()
        self._height = self.height()

        # Add coordinate display
        font = QtGui.QFont('Arial', 30, QtGui.QFont.Weight.Bold)
        self._coord_label = self.addText('', font)
        self._coord_label.setDefaultTextColor(QtGui.QColor(255, 0, 0))
        self._file_loaded = True

    def loadPoints(self, points: np.ndarray):
        """Load point annotations from array."""
        for p in points:
            point = PointAnnotation()
            self.addItem(point)
            point.setPoint(QtCore.QPointF(p[0], p[1]), self._point_count)
            self._point_items[self._point_count] = point
            self._point_count += 1

    def loadUTMPoints(self, utm_points: np.ndarray):
        """Load UTM coordinates for existing points."""
        for point_id, point in self._point_items.items():
            if point_id < len(utm_points):
                point._utm_coords = utm_points[point_id].tolist()

    def setInstruction(self, instruction: Instructions, sync: bool = True):
        """
        Set current annotation mode.

        Args:
            instruction: New annotation mode.
            sync: If True, synchronize with other plane.
        """
        viewer = self._viewer

        if instruction == Instructions.NO_INSTRUCTION:
            if self._current_point:
                self._point_items[self._point_count - 1] = self._current_point
                self._current_point = None

            if self._current_polygon and viewer.homography_matrix is not None:
                self._current_polygon.removeLastPoint()
                self._polygon_items[self._polygon_count - 1] = self._current_polygon
                self._current_polygon._updateLabel()
                self._current_polygon = None

                if sync:
                    self._syncInstructionToOtherPlane(instruction)

        elif instruction == Instructions.POINT and self._current_point is None:
            self._current_point = PointAnnotation()
            self.addItem(self._current_point)
            self._point_count += 1

        elif instruction == Instructions.POLYGON and self._current_polygon is None:
            if viewer.homography_matrix is not None:
                self._current_polygon = PolygonAnnotation(self)
                self.addItem(self._current_polygon)
                self._current_polygon.label = self._polygon_count
                self._polygon_count += 1

                if sync:
                    self._syncInstructionToOtherPlane(instruction)

        self._instruction = instruction
        self._showPoints()

    def _syncInstructionToOtherPlane(self, instruction: Instructions):
        """Synchronize instruction to the other plane."""
        if self._is_ground_plane:
            self._viewer._image_plane.scene.setInstruction(instruction, sync=False)
        else:
            self._viewer._ground_plane.scene.setInstruction(instruction, sync=False)

    def _showPoints(self):
        """Show all point annotations."""
        for point in self._point_items.values():
            point._grip.show()
            point._label.show()

    def deleteLastPoint(self):
        """Delete most recent point annotation."""
        if self._point_items:
            self._point_count -= 1
            point = self._point_items.pop(self._point_count)
            self.removeItem(point._grip)
            self.removeItem(point)

    def deleteLastPolygon(self, sync: bool = True):
        """Delete most recent polygon annotation."""
        if self._polygon_items:
            self._polygon_count -= 1
            polygon = self._polygon_items.pop(self._polygon_count)
            for grip in polygon._grips:
                self.removeItem(grip)
            self.removeItem(polygon)

            if sync:
                if self._is_ground_plane:
                    self._viewer._image_plane.scene.deleteLastPolygon(sync=False)
                else:
                    self._viewer._ground_plane.scene.deleteLastPolygon(sync=False)

    def getPoints(self) -> np.ndarray:
        """Return all point positions as array."""
        return np.array([p.position for p in self._point_items.values()])

    def getUTMPoints(self) -> np.ndarray:
        """Return all UTM positions as array."""
        if not self._is_ground_plane:
            raise RuntimeWarning('UTM coordinates only available on ground plane.')
        return np.array([p.utm_position for p in self._point_items.values()])

    def toNumpy(self, point: QtCore.QPointF) -> np.ndarray:
        """Convert QPointF to numpy array."""
        return np.array([[point.x(), point.y()]])

    def toQPointF(self, point: np.ndarray) -> QtCore.QPointF:
        """Convert numpy point to QPointF."""
        return QtCore.QPointF(point[0], point[1])

    def loadROI(self, filename: str):
        """Load ROI polygons from JSON file."""
        with open(filename, 'r') as f:
            self._roi_data = json.load(f)

        if self._viewer.homography_matrix is None:
            print('Cannot load ROI without homography matrix.')
            return

        for key, roi in self._roi_data.items():
            if key == 'group':
                continue

            points = np.array(roi['roi'])
            points[:, 0] *= self._width
            points[:, 1] *= self._height

            self._current_polygon = PolygonAnnotation(self)
            self._current_polygon.label = self._polygon_count
            self.addItem(self._current_polygon)

            # Create corresponding polygon on other plane
            if not self._is_ground_plane:
                other_scene = self._viewer._ground_plane.scene
                other_scene._current_polygon = PolygonAnnotation(other_scene)
                other_scene._current_polygon.label = self._polygon_count
                other_scene.addItem(other_scene._current_polygon)

            for p in points:
                self._addPolygonPoint(QtCore.QPointF(p[0], p[1]))

            # Finalize polygons
            self._current_polygon.removeLastPoint()
            self._polygon_items[self._polygon_count] = self._current_polygon
            self._current_polygon._updateLabel()

            if not self._is_ground_plane:
                other_scene._current_polygon.removeLastPoint()
                other_scene._polygon_items[other_scene._polygon_count] = other_scene._current_polygon
                other_scene._current_polygon._updateLabel()
                other_scene._polygon_count += 1

            self._polygon_count += 1
            self._current_polygon = None

            if not self._is_ground_plane:
                other_scene._current_polygon = None

    def _addPolygonPoint(self, pos: QtCore.QPointF):
        """Add point to current polygon with cross-plane synchronization."""
        self._current_polygon.removeLastPoint()
        self._current_polygon.addPoint(pos)
        self._current_polygon.addPoint(pos)

        if not self._is_ground_plane:
            # Reproject to ground plane
            reproj = self._viewer.reprojectToGround(self.toNumpy(pos))
            ground_pos = self.toQPointF(reproj[0])
            other = self._viewer._ground_plane.scene._current_polygon
            other.removeLastPoint()
            other.addPoint(ground_pos)
            other.addPoint(ground_pos)

    def mousePressEvent(self, event):
        """Handle mouse press for annotation."""
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)

        pos = event.scenePos()

        if self._instruction == Instructions.POINT:
            if self._current_point._grip is None:
                self._current_point.setPoint(pos, self._point_count - 1)

                if self._has_utm and self._elevation_map is not None:
                    x, y = int(pos.x()), int(pos.y())
                    utm_x, utm_y = pixel_to_utm((x, y), self._transform)
                    elevation = self._elevation_map[y, x]
                    self._current_point._utm_coords = [utm_x, utm_y, float(elevation)]

                self.setInstruction(Instructions.NO_INSTRUCTION)

        elif self._instruction == Instructions.POLYGON and self._viewer.homography_matrix is not None:
            # Hide points during polygon drawing
            for point in self._point_items.values():
                point._grip.hide()
                point._label.hide()

            self._addPolygonPointWithSync(pos)

        super().mousePressEvent(event)

    def _addPolygonPointWithSync(self, pos: QtCore.QPointF):
        """Add polygon point with synchronization to other plane."""
        self._current_polygon.removeLastPoint()
        self._current_polygon.addPoint(pos)
        self._current_polygon.addPoint(pos)

        np_pos = self.toNumpy(pos)

        if self._is_ground_plane:
            reproj = self._viewer.reprojectToImage(np_pos)
            other = self._viewer._image_plane.scene._current_polygon
        else:
            reproj = self._viewer.reprojectToGround(np_pos)
            other = self._viewer._ground_plane.scene._current_polygon

        other_pos = self.toQPointF(reproj[0])
        other.removeLastPoint()
        other.addPoint(other_pos)
        other.addPoint(other_pos)

    def mouseMoveEvent(self, event):
        """Update coordinate display and polygon preview."""
        pos = event.scenePos()
        x, y = int(pos.x()), int(pos.y())

        # Update coordinate display
        if 0 <= x <= self.width() and 0 <= y <= self.height() and self._coord_label:
            elevation = 0
            if self._is_ground_plane and self._elevation_map is not None:
                if 0 <= y < self._elevation_map.shape[0] and 0 <= x < self._elevation_map.shape[1]:
                    elevation = self._elevation_map[y, x]

            if self._has_utm:
                utm_x, utm_y = pixel_to_utm((x, y), self._transform)
                self._coord_label.setPlainText(f'{utm_x:.1f}, {utm_y:.1f}, {elevation:.1f}')
            else:
                self._coord_label.setPlainText(f'{x}, {y}, {elevation:.1f}')

            self._coord_label.setPos(pos)

        # Update polygon preview
        if self._instruction == Instructions.POLYGON and self._viewer.homography_matrix is not None:
            self._current_polygon.movePoint(self._current_polygon.num_points - 1, pos)

            np_pos = self.toNumpy(pos)
            if self._is_ground_plane:
                reproj = self._viewer.reprojectToImage(np_pos)
                other = self._viewer._image_plane.scene._current_polygon
            else:
                reproj = self._viewer.reprojectToGround(np_pos)
                other = self._viewer._ground_plane.scene._current_polygon

            other_pos = self.toQPointF(reproj[0])
            other.movePoint(other.num_points - 1, other_pos)

        super().mouseMoveEvent(event)


class HomographyViewer(QtWidgets.QGraphicsView):
    """Graphics view with zoom support for homography calibration."""

    rightMouseButtonPressed = pyqtSignal(float, float)
    rightMouseButtonReleased = pyqtSignal(float, float)
    rightMouseButtonDoubleClicked = pyqtSignal(float, float)

    def __init__(self, parent: 'AnnotationWindow', is_ground_plane: bool = False,
                 show_utm: bool = False):
        """
        Initialize viewer.

        Args:
            parent: Parent AnnotationWindow.
            is_ground_plane: True if this is ground plane viewer.
            show_utm: True to display UTM coordinates.
        """
        super().__init__(parent)
        self._viewer = parent  # Reference to main window for homography access

        self.setRenderHints(
            QtGui.QPainter.RenderHint.Antialiasing |
            QtGui.QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setMouseTracking(True)

        self._zoom_stack = []
        self._aspect_mode = Qt.AspectRatioMode.KeepAspectRatio
        self.scene = HomographyScene(parent, is_ground_plane, show_utm)
        self.setScene(self.scene)

        self.fitInView(self.scene._image_item, Qt.AspectRatioMode.KeepAspectRatio)

    def _updateView(self):
        """Update view based on zoom stack."""
        if self._zoom_stack and self.sceneRect().contains(self._zoom_stack[-1]):
            self.fitInView(self._zoom_stack[-1], Qt.AspectRatioMode.IgnoreAspectRatio)
        else:
            self._zoom_stack.clear()
            self.fitInView(self.sceneRect(), self._aspect_mode)

    def mousePressEvent(self, event):
        """Handle right-click zoom start."""
        if event.button() == Qt.MouseButton.RightButton:
            pos = self.mapToScene(event.pos())
            self.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
            self.rightMouseButtonPressed.emit(pos.x(), pos.y())
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle right-click zoom end."""
        if event.button() == Qt.MouseButton.RightButton:
            pos = self.mapToScene(event.pos())
            view_box = self._zoom_stack[-1] if self._zoom_stack else self.sceneRect()
            selection = self.scene.selectionArea().boundingRect().intersected(view_box)
            self.scene.setSelectionArea(QtGui.QPainterPath())

            if selection.isValid() and selection != view_box:
                self._zoom_stack.append(selection)
                self._updateView()

            self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
            self.rightMouseButtonReleased.emit(pos.x(), pos.y())
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Reset zoom on right double-click."""
        if event.button() == Qt.MouseButton.RightButton:
            self._zoom_stack.clear()
            self._updateView()
            pos = self.mapToScene(event.pos())
            self.rightMouseButtonDoubleClicked.emit(pos.x(), pos.y())
        super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event):
        """Update view on resize."""
        self._updateView()


class ImagePopup(QtWidgets.QDialog):
    """Dialog for displaying homography result images."""

    def __init__(self, parent=None):
        """Initialize popup dialog."""
        super().__init__(parent)
        self.setWindowTitle('Homography Result')

        self._warped_label = QtWidgets.QLabel()
        self._reproj_label = QtWidgets.QLabel()

        layout = QVBoxLayout()
        layout.addWidget(self._warped_label)
        layout.addWidget(self._reproj_label)
        self.setLayout(layout)

    def setImage(self, img: np.ndarray, is_reprojection: bool = False):
        """Display image in dialog."""
        cv2.imwrite('result_reprojection.jpg', img)
        pixmap = convert_cv_to_qt(img)

        if is_reprojection:
            self._reproj_label.setPixmap(pixmap)
        else:
            self._warped_label.setPixmap(pixmap)

    def reset(self):
        """Clear displayed images."""
        self._warped_label.clear()
        self._reproj_label.clear()


class AnnotationWindow(QtWidgets.QMainWindow):
    """Main application window for homography estimation."""

    SEEK_MILLISECONDS = 1000

    def __init__(self, parent=None):
        """Initialize main window with dual-plane viewers."""
        super().__init__(parent)
        self.setWindowTitle('Homography Estimation Tool')

        self._image_plane = HomographyViewer(self)
        self._ground_plane = HomographyViewer(self, is_ground_plane=True, show_utm=True)
        self._popup = ImagePopup(self)

        self.homography_matrix = None
        self._filename = None

        self._setupUI()
        self._setupMenus()
        self._setupShortcuts()

    def _setupUI(self):
        """Setup main layout and controls."""
        # Viewer layout
        viewer_layout = QVBoxLayout()
        viewer_layout.setContentsMargins(0, 0, 0, 0)
        viewer_layout.addWidget(self._image_plane)
        viewer_layout.addWidget(self._ground_plane)

        # Buttons
        buttons = [
            ('Delete Last Point - Image', partial(self._deleteLastPoint, self._image_plane)),
            ('Delete Last Point - Ground', partial(self._deleteLastPoint, self._ground_plane)),
            ('Delete Last Polygon', partial(self._deleteLastPolygon, self._ground_plane)),
            ('Homography', self._computeHomography),
            ('Load Homography', self._loadHomography),
            ('Save Progress', self._saveProgress),
            ('Save Polygons', self._savePolygons),
            ('Reproj Error', self._computeReprojectionError),
            ('Load Points', self._loadPoints),
            ('Load ROI', self._loadROI),
            ('Load Camera', self._loadCameraParams),
            ('Calibrate', self._calibrateCamera),
        ]

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)

        for text, callback in buttons:
            btn = QPushButton(text)
            btn.clicked.connect(callback)
            button_layout.addWidget(btn)

        # Error label
        self._error_label = QtWidgets.QLabel()
        button_layout.addWidget(QtWidgets.QLabel('Homography error: '))
        button_layout.addWidget(self._error_label)

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.addLayout(viewer_layout)
        main_layout.addLayout(button_layout)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    def _setupMenus(self):
        """Create menu bar."""
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction("&Load Image Plane Image", partial(self._loadImage, self._image_plane))
        file_menu.addAction("&Load Ground Plane Image", partial(self._loadImage, self._ground_plane))

        instruction_menu = self.menuBar().addMenu("Instructions")
        instruction_menu.addAction("Point - Image Plane",
                                   partial(self._image_plane.scene.setInstruction, Instructions.POINT))
        instruction_menu.addAction("Point - Ground Plane",
                                   partial(self._ground_plane.scene.setInstruction, Instructions.POINT))
        instruction_menu.addAction("Polygon - Ground Plane",
                                   partial(self._ground_plane.scene.setInstruction, Instructions.POLYGON))

    def _setupShortcuts(self):
        """Setup keyboard shortcuts."""
        shortcuts = [
            (Qt.Key.Key_Space, self._togglePlayback),
            (Qt.Key.Key_Right, self._seekForward),
            (Qt.Key.Key_Left, self._seekBackward),
            (Qt.Key.Key_I, partial(self._image_plane.scene.setInstruction, Instructions.POINT)),
            (Qt.Key.Key_G, partial(self._ground_plane.scene.setInstruction, Instructions.POINT)),
            (Qt.Key.Key_P, partial(self._ground_plane.scene.setInstruction, Instructions.POLYGON)),
            (Qt.Key.Key_Escape, partial(self._ground_plane.scene.setInstruction, Instructions.NO_INSTRUCTION)),
            (Qt.Key.Key_C, self._resetAll),
            (Qt.Key.Key_S, self._saveProgress),
        ]
        for key, callback in shortcuts:
            QtGui.QShortcut(key, self, activated=callback)

    def reprojectToGround(self, points: np.ndarray) -> np.ndarray:
        """Reproject points from image to ground plane."""
        homogeneous = np.hstack((points, np.ones((points.shape[0], 1))))
        transformed = homogeneous @ self.homography_matrix.T
        return transformed[:, :2] / transformed[:, [2]]

    def reprojectToImage(self, points: np.ndarray) -> np.ndarray:
        """Reproject points from ground to image plane."""
        homogeneous = np.hstack((points, np.ones((points.shape[0], 1))))
        inv_matrix = np.linalg.inv(self.homography_matrix)
        transformed = homogeneous @ inv_matrix.T
        return transformed[:, :2] / transformed[:, [2]]

    def _loadImage(self, viewer: HomographyViewer):
        """Load image into viewer."""
        formats = '*.png *.jpg *.bmp *.tif *.tiff'
        if viewer == self._image_plane:
            formats += ' *.avi *.mp4'

        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Image",
            QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.PicturesLocation),
            f"Image Files ({formats})"
        )

        if filename:
            viewer.scene.loadImage(filename)
            item = viewer.scene._video_item if viewer.scene._media_type == 'video' else viewer.scene._image_item
            viewer.fitInView(item, Qt.AspectRatioMode.KeepAspectRatio)
            viewer.centerOn(item)

            if viewer == self._image_plane:
                self._filename = filename

    def _deleteLastPoint(self, viewer: HomographyViewer):
        """Delete last point from viewer."""
        viewer.scene.deleteLastPoint()

    def _deleteLastPolygon(self, viewer: HomographyViewer):
        """Delete last polygon from viewer."""
        viewer.scene.deleteLastPolygon()

    def _computeHomography(self):
        """Compute and display homography matrix."""
        image_pts = self._image_plane.scene.getPoints()
        ground_pts = self._ground_plane.scene.getPoints()

        if len(image_pts) < 4 or len(ground_pts) < 4 or len(image_pts) != len(ground_pts):
            return

        self.homography_matrix, _ = cv2.findHomography(image_pts, ground_pts)

        # Load and warp image
        if self._image_plane.scene._media_type == 'image':
            cv_image = cv2.imread(self._image_plane.scene._filename)
        else:
            cap = cv2.VideoCapture(self._image_plane.scene._filename)
            _, cv_image = cap.read()
            cap.release()

        # Load ground image
        if '.tif' in self._ground_plane.scene._filename:
            ortho = rasterio.open(self._ground_plane.scene._filename)
            r, g, b = ortho.read(1), ortho.read(2), ortho.read(3)
            cv_ground = np.dstack((b, g, r))
        else:
            cv_ground = cv2.imread(self._ground_plane.scene._filename)

        # Create blended result
        warped = cv2.warpPerspective(cv_image, self.homography_matrix,
                                     (cv_ground.shape[1], cv_ground.shape[0]))
        result = cv2.addWeighted(warped, 0.7, cv_ground, 0.3, 0)
        self._popup.setImage(result)

        # Draw reprojection
        reproj_pts = self.reprojectToGround(image_pts)
        for orig, reproj in zip(ground_pts.astype(int), reproj_pts.astype(int)):
            cv2.circle(cv_ground, tuple(orig), 2, (0, 255, 0), 2)
            cv2.circle(cv_ground, tuple(reproj), 2, (0, 0, 255), 2)

        self._popup.setImage(cv_ground, is_reprojection=True)
        self._popup.show()

    def _computeReprojectionError(self):
        """Compute and display reprojection error."""
        if self.homography_matrix is None:
            self._error_label.setText('ERROR!')
            return

        image_pts = self._image_plane.scene.getPoints()
        ground_pts = self._ground_plane.scene.getPoints()
        reproj_pts = self.reprojectToGround(image_pts)

        errors = np.linalg.norm(reproj_pts - ground_pts, axis=1)
        rmse = np.sqrt(np.mean(errors ** 2))
        self._error_label.setText(f'{rmse:.2f}')

    def _loadHomography(self):
        """Load homography matrix from file."""
        if not (self._image_plane.scene._file_loaded and self._ground_plane.scene._file_loaded):
            QMessageBox.warning(self, 'Warning', 'Load both images first.')
            return

        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Homography File", QtCore.QDir.homePath()
        )
        if filename:
            self.homography_matrix = np.loadtxt(filename).astype(float)

    def _loadPoints(self):
        """Load point annotations from file."""
        if not (self._image_plane.scene._file_loaded and self._ground_plane.scene._file_loaded):
            QMessageBox.warning(self, 'Warning', 'Load both images first.')
            return

        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Points File", QtCore.QDir.homePath()
        )
        if filename:
            image_pts = np.loadtxt(filename)
            ground_pts = np.loadtxt(filename.replace('image_points', 'ground_points'))

            self._image_plane.scene.loadPoints(image_pts)
            self._ground_plane.scene.loadPoints(ground_pts)

            if self._ground_plane.scene._has_utm:
                georef_pts = np.loadtxt(filename.replace('image_points', 'georef_points'))
                self._ground_plane.scene.loadUTMPoints(georef_pts)

    def _loadROI(self):
        """Load ROI polygons from file."""
        if not (self._image_plane.scene._file_loaded and self._ground_plane.scene._file_loaded):
            QMessageBox.warning(self, 'Warning', 'Load both images first.')
            return

        if self.homography_matrix is None:
            QMessageBox.warning(self, 'Warning', 'Compute homography first.')
            return

        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open ROI File", QtCore.QDir.homePath()
        )
        if filename:
            self._image_plane.scene.loadROI(filename)

    def _loadCameraParams(self):
        """Load camera parameters for MATLAB calibration."""
        if MATLAB_ENGINE is None:
            QMessageBox.warning(self, 'Warning', 'MATLAB engine not available.')
            return

        if not (self._ground_plane.scene._file_loaded and self._ground_plane.scene._has_utm):
            QMessageBox.warning(self, 'Warning', 'Load orthophoto with georeferencing first.')
            return

        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Camera Parameters", QtCore.QDir.homePath()
        )
        if filename:
            MATLAB_ENGINE.eval(f"load('{filename}')", nargout=0)

    def _calibrateCamera(self):
        """Perform camera calibration using MATLAB."""
        if MATLAB_ENGINE is None:
            QMessageBox.warning(self, 'Warning', 'MATLAB engine not available.')
            return

        try:
            if not (self._image_plane.scene._point_items and
                    self._ground_plane.scene._point_items and
                    self._ground_plane.scene._has_utm):
                return

            import matlab

            image_pts = self._image_plane.scene.getPoints()
            georef_pts = self._ground_plane.scene.getUTMPoints()

            img_mat = matlab.double(image_pts.tolist())
            world_mat = matlab.double(georef_pts.tolist())

            intrinsics = MATLAB_ENGINE.eval("cameraParams.Intrinsics", nargout=1)
            MATLAB_ENGINE.workspace["worldPoints_mat"] = world_mat
            MATLAB_ENGINE.workspace["imagePoints_mat"] = img_mat
            MATLAB_ENGINE.workspace["imagePoints_mat_undistored"] = MATLAB_ENGINE.undistortPoints(
                img_mat, intrinsics
            )
            MATLAB_ENGINE.workspace["worldPose"] = MATLAB_ENGINE.estworldpose(
                MATLAB_ENGINE.workspace["imagePoints_mat_undistored"],
                world_mat, intrinsics,
                "MaxNumTrials", matlab.single(5000),
                "Confidence", matlab.single(95),
                "MaxReprojectionError", matlab.single(3),
                nargout=1
            )

            # Save calibration results
            K = np.array(MATLAB_ENGINE.eval("cameraParams.Intrinsics.K"))
            R = np.array(MATLAB_ENGINE.eval("worldPose.R"))
            t = np.array(MATLAB_ENGINE.eval("worldPose.Translation")).reshape((3, 1))

            output_dir = os.path.splitext(os.path.basename(self._filename))[0]
            os.makedirs(output_dir, exist_ok=True)

            np.savetxt(os.path.join(output_dir, 'K.txt'), K, fmt='%.10f')
            np.savetxt(os.path.join(output_dir, 'R.txt'), R, fmt='%.10f')
            np.savetxt(os.path.join(output_dir, 't.txt'), t, fmt='%.10f')

        except Exception as e:
            print(f'Calibration error: {e}')

    def _saveProgress(self):
        """Save point annotations and homography."""
        if not (self._image_plane.scene._point_items and self._ground_plane.scene._point_items):
            return

        output_dir = os.path.splitext(os.path.basename(self._filename))[0]
        os.makedirs(output_dir, exist_ok=True)

        np.savetxt(os.path.join(output_dir, 'image_points.txt'),
                   self._image_plane.scene.getPoints(), fmt='%d')
        np.savetxt(os.path.join(output_dir, 'ground_points.txt'),
                   self._ground_plane.scene.getPoints(), fmt='%d')

        if self.homography_matrix is not None:
            np.savetxt(os.path.join(output_dir, 'homography.txt'),
                       self.homography_matrix, fmt='%.5f')

        if self._ground_plane.scene._has_utm:
            np.savetxt(os.path.join(output_dir, 'georef_points.txt'),
                       self._ground_plane.scene.getUTMPoints(), fmt='%d')

    def _savePolygons(self):
        """Save polygon ROIs to JSON."""
        if not self._image_plane.scene._roi_data:
            return

        for label, polygon in self._image_plane.scene._polygon_items.items():
            pts = polygon.vertices
            pts[:, 0] /= self._image_plane.scene._width
            pts[:, 1] /= self._image_plane.scene._height
            self._image_plane.scene._roi_data[str(label + 1)]['roi'] = pts.tolist()

        output_file = f"{os.path.splitext(os.path.basename(self._filename))[0]}.json"
        with open(output_file, 'w') as f:
            json.dump(self._image_plane.scene._roi_data, f, indent=2)

    def _resetAll(self):
        """Reset all annotations."""
        self._saveProgress()

        for scene in (self._image_plane.scene, self._ground_plane.scene):
            while scene._point_count > 0:
                scene.deleteLastPoint()
            while scene._polygon_count > 0:
                scene.deleteLastPolygon(sync=False)
            scene.clear()
            scene._reset()

        self.homography_matrix = None
        self._error_label.setText('')
        self._filename = None
        self._popup.reset()

    def _togglePlayback(self):
        """Toggle video play/pause."""
        player = self._image_plane.scene.player
        if self._image_plane.scene._media_type == 'video':
            if player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                player.pause()
            else:
                player.play()

    def _seekForward(self):
        """Seek video forward."""
        if self._image_plane.scene._media_type == 'video':
            player = self._image_plane.scene.player
            new_pos = min(player.position() + self.SEEK_MILLISECONDS, player.duration())
            player.setPosition(new_pos)

    def _seekBackward(self):
        """Seek video backward."""
        if self._image_plane.scene._media_type == 'video':
            player = self._image_plane.scene.player
            new_pos = max(0, player.position() - self.SEEK_MILLISECONDS)
            player.setPosition(new_pos)


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = AnnotationWindow()
    window.showMaximized()
    sys.exit(app.exec())
