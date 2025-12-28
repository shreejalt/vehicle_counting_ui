"""
Polygon and Rectangle Annotation Tool for ROI annotation on images and videos.

A PyQt6-based GUI tool for drawing and managing rectangular bounding boxes
and polygon regions on images/videos, useful for object detection and segmentation.
"""

import json
import sys
from enum import Enum
from functools import partial

import numpy as np
from PyQt6 import QtWidgets, QtGui, QtCore, QtMultimedia, QtMultimediaWidgets
from PyQt6.QtCore import Qt, QPointF, QUrl
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtWidgets import (
    QHBoxLayout, QPushButton, QVBoxLayout, QWidget, QSlider, QLabel, QStyle
)

QtGui.QImageReader.setAllocationLimit(0)


class Instructions(Enum):
    """Annotation mode instructions."""
    NO_INSTRUCTION = 0
    RECTANGLE = 1
    POLYGON = 2


class GripItem(QtWidgets.QGraphicsPathItem):
    """
    Draggable control point for annotation vertices.

    Provides visual feedback on hover and notifies parent annotation
    when position changes.
    """

    _circle = QtGui.QPainterPath()
    _circle.addEllipse(QtCore.QRectF(-10, -10, 20, 20))
    _square = QtGui.QPainterPath()
    _square.addRect(QtCore.QRectF(-15, -15, 30, 30))

    def __init__(self, annotation_item, index_or_corner):
        """
        Initialize grip item.

        Args:
            annotation_item: Parent annotation (Rectangle or Polygon).
            index_or_corner: Vertex index (int) for polygon or corner name (str) for rectangle.
        """
        super().__init__()
        self._annotation = annotation_item
        self._index_or_corner = index_or_corner

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
        """Notify parent when position changes."""
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.isEnabled():
            self._annotation.movePoint(self._index_or_corner, value)
        return super().itemChange(change, value)


class RectangleAnnotation(QtWidgets.QGraphicsRectItem):
    """
    Interactive rectangle annotation with draggable corners.

    Displays corner coordinates and dimensions in real-time.
    """

    def __init__(self, parent=None):
        """Initialize rectangle annotation."""
        super().__init__(parent)

        self.setZValue(10)
        self.setPen(QtGui.QPen(QtGui.QColor('green'), 2))
        self.setAcceptHoverEvents(True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))

        self._top_left = None
        self._bottom_right = None
        self._top_left_grip = None
        self._bottom_right_grip = None

        # Coordinate labels
        font = QtGui.QFont('Arial', 30, QtGui.QFont.Weight.Bold)

        self._top_left_label = QtWidgets.QGraphicsTextItem('', self)
        self._top_left_label.setDefaultTextColor(QtGui.QColor(0, 255, 0))
        self._top_left_label.setFont(font)

        self._bottom_right_label = QtWidgets.QGraphicsTextItem('', self)
        self._bottom_right_label.setDefaultTextColor(QtGui.QColor(0, 255, 0))
        self._bottom_right_label.setFont(font)

        self._size_label = QtWidgets.QGraphicsTextItem('', self)
        self._size_label.setDefaultTextColor(QtGui.QColor(0, 0, 255))
        self._size_label.setFont(font)

    @property
    def points(self) -> list:
        """Return rectangle coordinates as [x1, y1, x2, y2]."""
        return [self._top_left.x(), self._top_left.y(),
                self._bottom_right.x(), self._bottom_right.y()]

    def setTopLeft(self, pos: QPointF):
        """Set top-left corner position."""
        self._top_left = self.mapFromScene(pos)
        self._top_left_grip = GripItem(self, 'top_left')
        self.scene().addItem(self._top_left_grip)
        self._top_left_grip.setPos(pos)
        self._updateLabels()

    def setBottomRight(self, pos: QPointF):
        """Set bottom-right corner position."""
        self._bottom_right = self.mapFromScene(pos)
        self._bottom_right_grip = GripItem(self, 'bottom_right')
        self.scene().addItem(self._bottom_right_grip)
        self._bottom_right_grip.setPos(pos)
        self._updateLabels()

    def movePoint(self, corner: str, pos: QPointF):
        """Move a corner point and update rectangle."""
        mapped_pos = self.mapFromScene(pos)

        if corner == 'top_left' and self._top_left is not None:
            self._top_left = mapped_pos
            if self._bottom_right is not None:
                self.setRect(QtCore.QRectF(self._top_left, self._bottom_right))
        elif corner == 'bottom_right' and self._bottom_right is not None:
            self._bottom_right = mapped_pos
            self.setRect(QtCore.QRectF(self._top_left, self._bottom_right))

        self._updateLabels()

    def setPoint(self, pos: QPointF):
        """Update rectangle during drawing (before bottom-right is set)."""
        if self._top_left is not None:
            mapped = self.mapFromScene(pos)
            if mapped.x() >= self._top_left.x() and mapped.y() >= self._top_left.y():
                self.setRect(QtCore.QRectF(self._top_left, mapped))
            self._updatePreviewLabels(mapped)

    def _updateLabels(self):
        """Update coordinate and size labels."""
        if self._top_left:
            self._top_left_label.setPlainText(f'{self._top_left.x():.1f}, {self._top_left.y():.1f}')
            self._top_left_label.setPos(self._top_left)

        if self._bottom_right:
            self._bottom_right_label.setPlainText(f'{self._bottom_right.x():.1f}, {self._bottom_right.y():.1f}')
            self._bottom_right_label.setPos(self._bottom_right)

        if self._top_left and self._bottom_right:
            width = self._bottom_right.x() - self._top_left.x()
            height = self._bottom_right.y() - self._top_left.y()
            center_x = (self._top_left.x() + self._bottom_right.x()) / 2 - 50
            center_y = (self._top_left.y() + self._bottom_right.y()) / 2
            self._size_label.setPlainText(f'{width:.1f} x {height:.1f}')
            self._size_label.setPos(center_x, center_y)

    def _updatePreviewLabels(self, pos: QPointF):
        """Update labels during rectangle drawing preview."""
        self._bottom_right_label.setPlainText(f'{pos.x():.1f}, {pos.y():.1f}')
        self._bottom_right_label.setPos(pos)

        if self._top_left:
            width = pos.x() - self._top_left.x()
            height = pos.y() - self._top_left.y()
            center_x = (self._top_left.x() + pos.x()) / 2 - 50
            center_y = (self._top_left.y() + pos.y()) / 2
            self._size_label.setPlainText(f'{width:.1f} x {height:.1f}')
            self._size_label.setPos(center_x, center_y)

    def _syncGrips(self):
        """Synchronize grip positions with rectangle corners."""
        if self._top_left_grip:
            self._top_left_grip.setEnabled(False)
            self._top_left_grip.setPos(self.mapToScene(self.rect().topLeft()))
            self._top_left_grip.setEnabled(True)
            self._top_left = self.mapToScene(self.rect().topLeft())

        if self._bottom_right_grip:
            self._bottom_right_grip.setEnabled(False)
            self._bottom_right_grip.setPos(self.mapToScene(self.rect().bottomRight()))
            self._bottom_right_grip.setEnabled(True)
            self._bottom_right = self.mapToScene(self.rect().bottomRight())

        self._updateLabels()

    def itemChange(self, change, value):
        """Handle rectangle movement."""
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


class PolygonAnnotation(QtWidgets.QGraphicsPolygonItem):
    """
    Interactive polygon annotation with draggable vertices.

    Supports arbitrary number of vertices with real-time preview.
    """

    def __init__(self, parent=None):
        """Initialize polygon annotation."""
        super().__init__(parent)

        self._points = []
        self._grips = []
        self.label = 0

        self.setZValue(10)
        self.setPen(QtGui.QPen(QtGui.QColor("blue"), 2))
        self.setAcceptHoverEvents(True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))

        # ID label
        self._id_label = QtWidgets.QGraphicsTextItem('', self)
        self._id_label.setDefaultTextColor(QtGui.QColor(0, 0, 255))
        self._id_label.setFont(QtGui.QFont('Arial', 20, QtGui.QFont.Weight.Bold))

    @property
    def num_points(self) -> int:
        """Return number of vertices."""
        return len(self._grips)

    @property
    def points(self) -> list:
        """Return polygon vertices as list of [x, y] pairs."""
        return [[p.x(), p.y()] for p in self._points]

    @property
    def centroid(self) -> np.ndarray:
        """Return polygon centroid."""
        if not self._points:
            return np.array([0, 0])
        pts = np.array([[p.x(), p.y()] for p in self._points])
        return pts.mean(axis=0)

    def addPoint(self, pos: QPointF):
        """Add a vertex to the polygon."""
        self._points.append(pos)
        self.setPolygon(QtGui.QPolygonF(self._points))

        grip = GripItem(self, len(self._points) - 1)
        self.scene().addItem(grip)
        self._grips.append(grip)
        grip.setPos(pos)

    def removeLastPoint(self):
        """Remove the last vertex."""
        if self._points:
            self._points.pop()
            self.setPolygon(QtGui.QPolygonF(self._points))
            grip = self._grips.pop()
            self.scene().removeItem(grip)

    def movePoint(self, index: int, pos: QPointF):
        """Move a vertex to a new position."""
        if 0 <= index < len(self._points):
            self._points[index] = self.mapFromScene(pos)
            self.setPolygon(QtGui.QPolygonF(self._points))
            self._updateLabel()

    def _updateLabel(self):
        """Update label position to centroid."""
        center = self.centroid
        self._id_label.setPos(QPointF(center[0], center[1]))
        self._id_label.setPlainText(str(self.label + 1))

    def _moveGrip(self, index: int, pos: QPointF):
        """Move grip without triggering position change callback."""
        if 0 <= index < len(self._grips):
            grip = self._grips[index]
            grip.setEnabled(False)
            grip.setPos(pos)
            grip.setEnabled(True)

    def itemChange(self, change, value):
        """Handle polygon movement."""
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for i, point in enumerate(self._points):
                self._moveGrip(i, self.mapToScene(point))
            self._updateLabel()
        return super().itemChange(change, value)

    def hoverEnterEvent(self, event):
        """Highlight on hover."""
        self.setBrush(QtGui.QColor(0, 0, 255, 100))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Reset appearance on hover exit."""
        self.setBrush(QtGui.QBrush(Qt.BrushStyle.NoBrush))
        super().hoverLeaveEvent(event)


class AnnotationScene(QtWidgets.QGraphicsScene):
    """Graphics scene managing image/video, rectangle and polygon annotations."""

    def __init__(self, parent=None):
        """Initialize scene with image and video items."""
        super().__init__(parent)

        # Image item
        self._image_item = QtWidgets.QGraphicsPixmapItem()
        self._image_item.setCursor(QtGui.QCursor(Qt.CursorShape.CrossCursor))
        self.addItem(self._image_item)

        # Video player and item
        self.player = QtMultimedia.QMediaPlayer()
        self._video_item = QtMultimediaWidgets.QGraphicsVideoItem()
        self._video_item.setCursor(QtGui.QCursor(Qt.CursorShape.CrossCursor))
        self._video_item.setSize(QtCore.QSizeF(2560, 1440))
        self.player.setVideoOutput(self._video_item)
        self.addItem(self._video_item)
        self._video_item.hide()

        self._current_rect = None
        self._current_polygon = None
        self._rectangles = []
        self._polygons = []
        self._instruction = Instructions.NO_INSTRUCTION
        self._output_file = 'roi.json'
        self._media_type = None

        # Mouse coordinate display
        font = QtGui.QFont('Arial', 30, QtGui.QFont.Weight.Bold)
        self._coord_label = self.addText('', font)
        self._coord_label.setDefaultTextColor(QtGui.QColor(255, 0, 0))

    @property
    def image_item(self):
        """Return the image graphics item."""
        return self._image_item

    @property
    def video_item(self):
        """Return the video graphics item."""
        return self._video_item

    @property
    def media_size(self) -> QtCore.QSizeF:
        """Return current media size."""
        if self._media_type == 'video':
            return self._video_item.size()
        return QtCore.QSizeF(self._image_item.pixmap().size())

    def loadImage(self, filename: str):
        """Load and display an image."""
        self._video_item.hide()
        self._image_item.show()
        self._image_item.setPixmap(QtGui.QPixmap(filename))
        self.setSceneRect(self._image_item.boundingRect())
        self._media_type = 'image'

    def loadVideo(self, filename: str):
        """Load and display a video."""
        self._image_item.hide()
        self._video_item.show()
        self.player.setSource(QUrl.fromLocalFile(filename))
        self.setSceneRect(self._video_item.boundingRect())
        self._media_type = 'video'

    def setInstruction(self, instruction: Instructions):
        """Set current annotation mode."""
        # Finalize current annotation
        if instruction == Instructions.NO_INSTRUCTION:
            if self._current_rect:
                self._rectangles.append(self._current_rect)
                self._current_rect = None
            if self._current_polygon:
                self._current_polygon.removeLastPoint()
                self._current_polygon._updateLabel()
                self._polygons.append(self._current_polygon)
                self._current_polygon = None

        self._instruction = instruction

        # Start new annotation
        if instruction == Instructions.RECTANGLE:
            self._current_rect = RectangleAnnotation()
            self.addItem(self._current_rect)
        elif instruction == Instructions.POLYGON:
            self._current_polygon = PolygonAnnotation()
            self._current_polygon.label = len(self._polygons)
            self.addItem(self._current_polygon)

    def deleteLastRectangle(self):
        """Remove the most recently added rectangle."""
        if self._rectangles:
            rect = self._rectangles.pop()
            if rect._top_left_grip:
                self.removeItem(rect._top_left_grip)
            if rect._bottom_right_grip:
                self.removeItem(rect._bottom_right_grip)
            self.removeItem(rect)

    def deleteLastPolygon(self):
        """Remove the most recently added polygon."""
        if self._polygons:
            polygon = self._polygons.pop()
            for grip in polygon._grips:
                self.removeItem(grip)
            self.removeItem(polygon)

    def save(self):
        """Save all annotations to JSON file."""
        data = {
            'rectangles': {},
            'polygons': {}
        }

        for i, rect in enumerate(self._rectangles):
            data['rectangles'][i] = rect.points

        for i, polygon in enumerate(self._polygons):
            data['polygons'][i] = polygon.points

        with open(self._output_file, 'w') as f:
            json.dump(data, f, indent=2)

    def mousePressEvent(self, event):
        """Handle mouse press for annotation drawing."""
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)

        pos = event.scenePos()

        if self._instruction == Instructions.RECTANGLE and self._current_rect:
            if self._current_rect._top_left is None:
                self._current_rect.setTopLeft(pos)
            elif self._current_rect._bottom_right is None:
                self._current_rect.setBottomRight(pos)

        elif self._instruction == Instructions.POLYGON and self._current_polygon:
            self._current_polygon.removeLastPoint()
            self._current_polygon.addPoint(pos)
            self._current_polygon.addPoint(pos)

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Update coordinate display and annotation preview."""
        pos = event.scenePos()

        if self._instruction == Instructions.NO_INSTRUCTION:
            self._coord_label.setPlainText(f'{pos.x():.1f}, {pos.y():.1f}')
            self._coord_label.setPos(pos)
        else:
            self._coord_label.setPlainText('')

            if self._instruction == Instructions.RECTANGLE:
                if self._current_rect and self._current_rect._top_left and not self._current_rect._bottom_right:
                    self._current_rect.setPoint(pos)

            elif self._instruction == Instructions.POLYGON:
                if self._current_polygon and self._current_polygon.num_points > 0:
                    self._current_polygon.movePoint(self._current_polygon.num_points - 1, pos)

        super().mouseMoveEvent(event)


class AnnotationView(QtWidgets.QGraphicsView):
    """Graphics view with antialiasing and mouse tracking."""

    def __init__(self, parent=None):
        """Initialize view with rendering hints."""
        super().__init__(parent)
        self.setRenderHints(
            QtGui.QPainter.RenderHint.Antialiasing |
            QtGui.QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setMouseTracking(True)


class AnnotationWindow(QtWidgets.QMainWindow):
    """Main application window for polygon and rectangle annotation."""

    SEEK_MILLISECONDS = 1000

    def __init__(self, parent=None):
        """Initialize main window with scene and controls."""
        super().__init__(parent)
        self.setWindowTitle('Polygon & Rectangle Annotation Tool')

        self._view = AnnotationView()
        self._scene = AnnotationScene(self)
        self._view.setScene(self._scene)

        self._setupMenus()
        self._setupUI()
        self._setupShortcuts()
        self._connectSignals()

    def _setupMenus(self):
        """Create menu bar."""
        menu_file = self.menuBar().addMenu("File")
        menu_file.addAction("Open &Image", self._loadImage).setShortcut('Ctrl+I')
        menu_file.addAction("Open &Video", self._loadVideo).setShortcut('Ctrl+O')

        menu_tools = self.menuBar().addMenu("Tools")
        menu_tools.addAction("Rectangle", partial(self._scene.setInstruction, Instructions.RECTANGLE)).setShortcut('R')
        menu_tools.addAction("Polygon", partial(self._scene.setInstruction, Instructions.POLYGON)).setShortcut('P')

    def _setupUI(self):
        """Setup main layout and buttons."""
        # Play button
        self._play_btn = QPushButton()
        self._play_btn.setEnabled(False)
        self._play_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self._play_btn.clicked.connect(self._togglePlayback)

        # Position slider
        self._position_slider = QSlider(Qt.Orientation.Horizontal)
        self._position_slider.sliderMoved.connect(self._setPosition)

        # Time label
        self._time_label = QLabel('00:00:00 / 00:00:00')

        # Playback controls layout
        playback_layout = QHBoxLayout()
        playback_layout.addWidget(self._play_btn)
        playback_layout.addWidget(self._position_slider)
        playback_layout.addWidget(self._time_label)

        # Annotation buttons
        delete_rect_btn = QPushButton("Delete Last Rectangle")
        delete_rect_btn.clicked.connect(self._scene.deleteLastRectangle)

        delete_poly_btn = QPushButton("Delete Last Polygon")
        delete_poly_btn.clicked.connect(self._scene.deleteLastPolygon)

        save_btn = QPushButton("Save Progress")
        save_btn.clicked.connect(self._scene.save)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addWidget(delete_rect_btn)
        btn_layout.addWidget(delete_poly_btn)
        btn_layout.addWidget(save_btn)

        main_layout = QVBoxLayout()
        main_layout.addWidget(self._view)
        main_layout.addLayout(playback_layout)
        main_layout.addLayout(btn_layout)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    def _setupShortcuts(self):
        """Setup keyboard shortcuts."""
        shortcuts = [
            (Qt.Key.Key_Escape, partial(self._scene.setInstruction, Instructions.NO_INSTRUCTION)),
            (Qt.Key.Key_S, self._scene.save),
            (Qt.Key.Key_Space, self._togglePlayback),
            (Qt.Key.Key_Right, self._seekForward),
            (Qt.Key.Key_Left, self._seekBackward),
        ]
        for key, callback in shortcuts:
            QtGui.QShortcut(key, self, activated=callback)

    def _connectSignals(self):
        """Connect media player signals."""
        player = self._scene.player
        player.playbackStateChanged.connect(self._onPlaybackStateChanged)
        player.positionChanged.connect(self._onPositionChanged)
        player.durationChanged.connect(self._onDurationChanged)

    def _loadImage(self):
        """Open file dialog and load selected image."""
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Image",
            QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.PicturesLocation),
            "Image Files (*.png *.jpg *.bmp *.tif *.tiff)"
        )
        if filename:
            self._scene.loadImage(filename)
            self._view.fitInView(self._scene.image_item, Qt.AspectRatioMode.KeepAspectRatio)
            self._view.centerOn(self._scene.image_item)
            self._play_btn.setEnabled(False)

    def _loadVideo(self):
        """Open file dialog and load selected video."""
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Video",
            QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.MoviesLocation),
            "Video Files (*.mp4 *.avi *.mov *.mkv)"
        )
        if filename:
            self._scene.loadVideo(filename)
            self._play_btn.setEnabled(True)

    def _togglePlayback(self):
        """Toggle video play/pause."""
        if self._scene._media_type != 'video':
            return
        player = self._scene.player
        if player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            player.pause()
        else:
            player.play()

    def _seekForward(self):
        """Seek video forward."""
        if self._scene._media_type != 'video':
            return
        player = self._scene.player
        new_pos = min(player.position() + self.SEEK_MILLISECONDS, player.duration())
        player.setPosition(new_pos)

    def _seekBackward(self):
        """Seek video backward."""
        if self._scene._media_type != 'video':
            return
        player = self._scene.player
        new_pos = max(0, player.position() - self.SEEK_MILLISECONDS)
        player.setPosition(new_pos)

    def _setPosition(self, position: int):
        """Set video position from slider."""
        self._scene.player.setPosition(position)

    def _formatTime(self, ms: int) -> str:
        """Format milliseconds as HH:MM:SS."""
        seconds = ms / 1000
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f'{hours:02.0f}:{minutes:02.0f}:{seconds:05.2f}'

    def _onPositionChanged(self, position: int):
        """Update position slider and time label."""
        self._position_slider.setValue(position)
        duration = self._scene.player.duration()
        self._time_label.setText(f'{self._formatTime(position)} / {self._formatTime(duration)}')

    def _onDurationChanged(self, duration: int):
        """Update slider range."""
        self._position_slider.setRange(0, duration)

    def _onPlaybackStateChanged(self):
        """Update play button icon."""
        if self._scene.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            icon = QStyle.StandardPixmap.SP_MediaPause
        else:
            icon = QStyle.StandardPixmap.SP_MediaPlay
        self._play_btn.setIcon(self.style().standardIcon(icon))


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = AnnotationWindow()
    window.showMaximized()
    sys.exit(app.exec())
