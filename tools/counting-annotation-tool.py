"""
Video Counting Annotation Tool for lane-based vehicle counting.

A PyQt6-based GUI tool for counting vehicles in video streams with
support for multiple lanes and polygon-based regions of interest.
"""

import json
import os
import sys
from collections import defaultdict
from enum import Enum
from functools import partial

import numpy as np
from PyQt6 import QtWidgets, QtGui, QtCore, QtMultimedia, QtMultimediaWidgets
from PyQt6.QtCore import pyqtSignal, Qt, QUrl, QPointF
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSizePolicy, QSlider, QComboBox, QStyle,
    QVBoxLayout, QWidget, QMainWindow
)


class Instructions(Enum):
    """Annotation mode instructions."""
    NO_INSTRUCTION = 0
    POLYGON = 1


class GripItem(QtWidgets.QGraphicsPathItem):
    """
    Draggable control point for polygon vertices.

    Provides visual feedback on hover and notifies parent polygon
    when position changes.
    """

    _circle = QtGui.QPainterPath()
    _circle.addEllipse(QtCore.QRectF(-10, -10, 20, 20))
    _square = QtGui.QPainterPath()
    _square.addRect(QtCore.QRectF(-15, -15, 30, 30))

    def __init__(self, annotation_item: 'PolygonAnnotation', index: int):
        """
        Initialize grip item.

        Args:
            annotation_item: Parent polygon annotation.
            index: Vertex index in the polygon.
        """
        super().__init__()
        self._annotation = annotation_item
        self._index = index

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
            self._annotation.movePoint(self._index, value)
        return super().itemChange(change, value)


class PolygonAnnotation(QtWidgets.QGraphicsPolygonItem):
    """
    Interactive polygon annotation with click counting.

    Tracks total clicks and per-lane click counts for vehicle counting.
    """

    def __init__(self, main_window: 'VideoCountingAnnotation', parent=None):
        """
        Initialize polygon annotation.

        Args:
            main_window: Reference to main application window.
            parent: Parent graphics item.
        """
        super().__init__(parent)

        self._main_window = main_window
        self._points = []
        self._grips = []
        self.label = 0
        self.click_count = 0
        self.lane_counts = defaultdict(int)

        self.setZValue(10)
        self.setPen(QtGui.QPen(QtGui.QColor("green"), 2))
        self.setAcceptHoverEvents(True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCursor(QtGui.QCursor(Qt.CursorShape.PointingHandCursor))

        # Label display
        self._id_label = QtWidgets.QGraphicsTextItem('', self)
        self._id_label.setDefaultTextColor(QtGui.QColor(0, 255, 0))
        self._id_label.setFont(QtGui.QFont('Arial', 20, QtGui.QFont.Weight.Bold))

    @property
    def num_points(self) -> int:
        """Return number of vertices."""
        return len(self._grips)

    @property
    def centroid(self) -> np.ndarray:
        """Return polygon centroid."""
        if not self._points:
            return np.array([0, 0])
        points = np.array([[p.x(), p.y()] for p in self._points])
        return points.mean(axis=0)

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

    def mousePressEvent(self, event):
        """Handle click for counting."""
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._main_window.lanes_locked:
                self.click_count += 1

            if self._main_window.active_lane > 0:
                self.lane_counts[self._main_window.active_lane] += 1

            self._main_window.updateCountLabels()
        super().mousePressEvent(event)

    def hoverEnterEvent(self, event):
        """Highlight on hover."""
        self.setBrush(QtGui.QColor(255, 0, 0, 100))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Reset appearance on hover exit."""
        self.setBrush(QtGui.QBrush(Qt.BrushStyle.NoBrush))
        super().hoverLeaveEvent(event)


class AnnotationScene(QtWidgets.QGraphicsScene):
    """Graphics scene managing video and polygon annotations."""

    def __init__(self, main_window: 'VideoCountingAnnotation'):
        """
        Initialize scene with video player.

        Args:
            main_window: Reference to main application window.
        """
        super().__init__(main_window)
        self._main_window = main_window
        self._setupDefaults()

    def _setupDefaults(self):
        """Initialize default state."""
        self.player = QtMultimedia.QMediaPlayer()
        self._video_item = QtMultimediaWidgets.QGraphicsVideoItem()
        self._video_item.setCursor(QtGui.QCursor(Qt.CursorShape.CrossCursor))
        self._video_item.setSize(QtCore.QSizeF(2560, 1440))
        self.player.setVideoOutput(self._video_item)
        self.addItem(self._video_item)

        self._instruction = Instructions.NO_INSTRUCTION
        self._current_polygon = None
        self._polygons = []

    @property
    def video_size(self) -> QtCore.QSizeF:
        """Return video item size."""
        return self._video_item.size()

    def loadVideo(self, filename: str):
        """Load video file."""
        self.player.setSource(QUrl.fromLocalFile(filename))
        self.setSceneRect(self._video_item.boundingRect())

    def loadROI(self, filename: str):
        """
        Load regions of interest from JSON file.

        Args:
            filename: Path to JSON file containing ROI data.
        """
        with open(filename, 'r') as f:
            data = json.load(f)

        for key, roi_data in data.items():
            if key == 'group':
                continue

            polygon = PolygonAnnotation(self._main_window)
            polygon.label = len(self._polygons)
            polygon.click_count = int(roi_data.get('counts', 0))

            if 'lanes' in roi_data:
                polygon.lane_counts = {int(k): int(v) for k, v in roi_data['lanes'].items()}

            self.addItem(polygon)

            # Convert normalized coordinates to pixels
            points = np.array(roi_data['roi'])
            points[:, 0] *= self._video_item.size().width()
            points[:, 1] *= self._video_item.size().height()

            for point in points:
                polygon.removeLastPoint()
                polygon.addPoint(QPointF(point[0], point[1]))
                polygon.addPoint(QPointF(point[0], point[1]))

            polygon.removeLastPoint()
            polygon._updateLabel()
            self._polygons.append(polygon)
            self._main_window.addPolygonControls(polygon.label)

        self._main_window.updateCountLabels()

    def setInstruction(self, instruction: Instructions):
        """Set current annotation mode."""
        if instruction == Instructions.NO_INSTRUCTION and self._current_polygon:
            self._current_polygon.removeLastPoint()
            self._current_polygon._updateLabel()
            self._polygons.append(self._current_polygon)
            self._main_window.addPolygonControls(self._current_polygon.label)
            self._current_polygon = None

        self._instruction = instruction

        if instruction == Instructions.POLYGON:
            self._current_polygon = PolygonAnnotation(self._main_window)
            self._current_polygon.label = len(self._polygons)
            self.addItem(self._current_polygon)

    def deleteLastPolygon(self):
        """Remove the most recently added polygon."""
        if self._polygons:
            polygon = self._polygons.pop()
            for grip in polygon._grips:
                self.removeItem(grip)
            self.removeItem(polygon)

    def getPolygon(self, index: int) -> PolygonAnnotation:
        """Get polygon by index."""
        return self._polygons[index] if 0 <= index < len(self._polygons) else None

    def mousePressEvent(self, event):
        """Handle mouse press for polygon drawing."""
        if self._instruction == Instructions.POLYGON and event.button() == Qt.MouseButton.LeftButton:
            self._current_polygon.removeLastPoint()
            self._current_polygon.addPoint(event.scenePos())
            self._current_polygon.addPoint(event.scenePos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Update polygon preview during drawing."""
        if self._instruction == Instructions.POLYGON and self._current_polygon:
            self._current_polygon.movePoint(
                self._current_polygon.num_points - 1,
                event.scenePos()
            )
        super().mouseMoveEvent(event)

    def reset(self):
        """Reset scene to initial state."""
        self.clear()
        self._setupDefaults()


class VideoViewer(QtWidgets.QGraphicsView):
    """Graphics view with zoom support for video annotation."""

    rightMouseButtonPressed = pyqtSignal(float, float)
    rightMouseButtonReleased = pyqtSignal(float, float)
    rightMouseButtonDoubleClicked = pyqtSignal(float, float)

    def __init__(self, main_window: 'VideoCountingAnnotation'):
        """Initialize viewer with scene."""
        super().__init__(main_window)

        self.setRenderHints(
            QtGui.QPainter.RenderHint.Antialiasing |
            QtGui.QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setMouseTracking(True)

        self._zoom_stack = []
        self._aspect_mode = Qt.AspectRatioMode.KeepAspectRatio
        self.scene = AnnotationScene(main_window)
        self.setScene(self.scene)

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
        super().mouseReleaseEvent(event)
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


class VideoCountingAnnotation(QMainWindow):
    """Main application window for video vehicle counting."""

    NUM_LANES = 3
    SEEK_MILLISECONDS = 1000

    def __init__(self, parent=None):
        """Initialize main window with video viewer and controls."""
        super().__init__(parent)
        self.setWindowTitle('Video Counting Annotation Tool')

        self._viewer = VideoViewer(self)
        self._filename = None
        self._polygon_controls = {}
        self._group_polygons = {}
        self.lanes_locked = False
        self.active_lane = 0

        self._setupMenus()
        self._setupUI()
        self._setupShortcuts()
        self._connectSignals()

    def _setupMenus(self):
        """Create menu bar."""
        menubar = self.menuBar()

        file_menu = menubar.addMenu('File')
        file_menu.addAction('&Open Video/Image', self._openVideo).setShortcut('Ctrl+O')
        file_menu.addAction('&Exit', sys.exit).setShortcut('Ctrl+Q')

        controls_menu = menubar.addMenu('Controls')
        controls_menu.addAction(
            'Draw Polygon',
            partial(self._viewer.scene.setInstruction, Instructions.POLYGON)
        ).setShortcut('Ctrl+D')
        controls_menu.addAction('Save Polygon', self._save).setShortcut('Ctrl+S')

    def _setupUI(self):
        """Setup main layout and controls."""
        # Play button
        self._play_btn = QPushButton()
        self._play_btn.setEnabled(False)
        self._play_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self._play_btn.clicked.connect(self._togglePlayback)

        # Position slider
        self._position_slider = QSlider(Qt.Orientation.Horizontal)
        self._position_slider.sliderMoved.connect(self._setPosition)

        # Time label
        self._time_label = QLabel('00:00:00/00:00:00')

        # Lane selector
        self._lane_combo = QComboBox()
        self._lane_combo.addItem('No Lane')
        for i in range(self.NUM_LANES):
            self._lane_combo.addItem(str(i + 1))
        self._lane_combo.activated.connect(self._onLaneChanged)

        # Control buttons
        delete_btn = QPushButton('Delete Last Polygon')
        delete_btn.clicked.connect(self._deleteLastPolygon)

        save_btn = QPushButton('Save Progress')
        save_btn.clicked.connect(self._save)

        load_roi_btn = QPushButton('Load ROI')
        load_roi_btn.clicked.connect(self._loadROI)

        reset_btn = QPushButton('Reset Counts')
        reset_btn.clicked.connect(self._resetCounts)

        self._lock_btn = QPushButton('Lock Lanes')
        self._lock_btn.clicked.connect(self._toggleLaneLock)

        # Layouts
        control_layout = QHBoxLayout()
        control_layout.addWidget(self._play_btn)
        control_layout.addWidget(self._position_slider)
        control_layout.addWidget(self._time_label)

        button_layout = QHBoxLayout()
        button_layout.addWidget(delete_btn)
        button_layout.addWidget(save_btn)
        button_layout.addWidget(load_roi_btn)
        button_layout.addWidget(reset_btn)
        button_layout.addWidget(self._lane_combo)
        button_layout.addWidget(self._lock_btn)

        self._count_layout1 = QHBoxLayout()
        self._count_layout2 = QHBoxLayout()

        count_layout = QVBoxLayout()
        count_layout.addLayout(self._count_layout1)
        count_layout.addLayout(self._count_layout2)

        main_layout = QVBoxLayout()
        main_layout.addWidget(self._viewer)
        main_layout.addLayout(control_layout)
        main_layout.addLayout(button_layout)
        main_layout.addLayout(count_layout)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        self._error_label = QLabel()
        self._error_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

    def _setupShortcuts(self):
        """Setup keyboard shortcuts."""
        shortcuts = [
            (Qt.Key.Key_Escape, partial(self._viewer.scene.setInstruction, Instructions.NO_INSTRUCTION)),
            (Qt.Key.Key_Space, self._togglePlayback),
            (Qt.Key.Key_Right, self._seekForward),
            (Qt.Key.Key_Left, self._seekBackward),
            (Qt.Key.Key_G, self._groupPolygons),
            (Qt.Key.Key_C, self._resetAll),
        ]
        for key, callback in shortcuts:
            QtGui.QShortcut(key, self, activated=callback)

    def _connectSignals(self):
        """Connect media player signals."""
        player = self._viewer.scene.player
        player.playbackStateChanged.connect(self._onPlaybackStateChanged)
        player.positionChanged.connect(self._onPositionChanged)
        player.durationChanged.connect(self._onDurationChanged)
        player.errorOccurred.connect(self._onError)

    def addPolygonControls(self, label: int):
        """Add count controls for a polygon."""
        # Delete count button
        delete_btn = QPushButton(f'Delete Last Count P{label + 1}')
        delete_btn.clicked.connect(partial(self._deleteLastCount, label))

        # Count label
        count_label = QLabel(f'PC{label + 1}: ')
        count_value = QLabel('')
        count_edit = QLineEdit()

        # Count layout
        count_layout = QHBoxLayout()
        count_layout.addWidget(delete_btn)
        count_layout.addWidget(count_label)
        count_layout.addWidget(count_value)
        count_layout.addWidget(count_edit)

        # Lane controls
        lane_layout = QHBoxLayout()
        for i in range(self.NUM_LANES):
            lane_layout.addWidget(QLabel(f'L{i + 1}: '))
            lane_layout.addWidget(QLabel(''))
            lane_layout.addWidget(QLineEdit())

        # Parent layout
        parent_layout = QVBoxLayout()
        parent_layout.addLayout(count_layout)
        parent_layout.addLayout(lane_layout)

        target_layout = self._count_layout1 if len(self._polygon_controls) % 2 == 0 else self._count_layout2
        target_layout.addLayout(parent_layout)

        self._polygon_controls[label] = (count_layout, lane_layout)

    def updateCountLabels(self):
        """Update all count display labels."""
        for label, (count_layout, lane_layout) in self._polygon_controls.items():
            polygon = self._viewer.scene.getPolygon(label)
            if polygon:
                count_layout.itemAt(2).widget().setText(str(polygon.click_count))

                for i in range(lane_layout.count()):
                    if i % 3 == 1:
                        lane_num = (i // 3) + 1
                        lane_layout.itemAt(i).widget().setText(
                            str(polygon.lane_counts.get(lane_num, 0))
                        )

    def _togglePlayback(self):
        """Toggle video play/pause."""
        player = self._viewer.scene.player
        if player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            player.pause()
        else:
            player.play()

    def _seekForward(self):
        """Seek video forward."""
        player = self._viewer.scene.player
        new_pos = min(player.position() + self.SEEK_MILLISECONDS, player.duration())
        player.setPosition(new_pos)

    def _seekBackward(self):
        """Seek video backward."""
        player = self._viewer.scene.player
        new_pos = max(0, player.position() - self.SEEK_MILLISECONDS)
        player.setPosition(new_pos)

    def _setPosition(self, position: int):
        """Set video position from slider."""
        self._viewer.scene.player.setPosition(position)

    def _formatTime(self, ms: int) -> str:
        """Format milliseconds as HH:MM:SS.ss."""
        seconds = ms / 1000
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f'{hours:02.0f}:{minutes:02.0f}:{seconds:05.2f}'

    def _onPositionChanged(self, position: int):
        """Update position slider and time label."""
        self._position_slider.setValue(position)
        duration = self._viewer.scene.player.duration()
        self._time_label.setText(f'{self._formatTime(position)} / {self._formatTime(duration)}')

    def _onDurationChanged(self, duration: int):
        """Update slider range."""
        self._position_slider.setRange(0, duration)

    def _onPlaybackStateChanged(self):
        """Update play button icon."""
        if self._viewer.scene.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            icon = QStyle.StandardPixmap.SP_MediaPause
        else:
            icon = QStyle.StandardPixmap.SP_MediaPlay
        self._play_btn.setIcon(self.style().standardIcon(icon))

    def _onError(self):
        """Handle media player error."""
        self._play_btn.setEnabled(False)
        self._error_label.setText(f'Error: {self._viewer.scene.player.errorString()}')

    def _onLaneChanged(self, index: int):
        """Handle lane selection change."""
        if self.active_lane > 0 and index == 0:
            self._consolidateLaneCounts()
        self.active_lane = index

    def _consolidateLaneCounts(self):
        """Add lane counts to total count when switching from lane mode."""
        for label in self._polygon_controls:
            polygon = self._viewer.scene.getPolygon(label)
            if polygon:
                polygon.click_count += sum(polygon.lane_counts.values())
        self.updateCountLabels()

    def _toggleLaneLock(self):
        """Toggle lane counting lock."""
        self.lanes_locked = not self.lanes_locked
        self._lock_btn.setText('Unlock Lanes' if self.lanes_locked else 'Lock Lanes')

    def _deleteLastCount(self, label: int):
        """Decrement count for a polygon."""
        polygon = self._viewer.scene.getPolygon(label)
        if polygon:
            if self.active_lane > 0:
                polygon.lane_counts[self.active_lane] = max(0, polygon.lane_counts[self.active_lane] - 1)
            if not self.lanes_locked:
                polygon.click_count = max(0, polygon.click_count - 1)
        self.updateCountLabels()

    def _deleteLastPolygon(self):
        """Delete last polygon and its controls."""
        if not self._polygon_controls:
            return

        self._viewer.scene.deleteLastPolygon()
        last_label = max(self._polygon_controls.keys())

        count_layout, lane_layout = self._polygon_controls[last_label]

        for layout in (count_layout, lane_layout):
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

        del self._polygon_controls[last_label]

    def _resetCounts(self):
        """Reset all polygon counts."""
        for label in self._polygon_controls:
            polygon = self._viewer.scene.getPolygon(label)
            if polygon:
                polygon.click_count = 0
                polygon.lane_counts.clear()
        self.updateCountLabels()

    def _resetAll(self):
        """Reset entire scene."""
        self._group_polygons.clear()
        self._viewer.scene.reset()

        while self._polygon_controls:
            self._deleteLastPolygon()

        self._time_label.setText('00:00:00/00:00:00')
        self._position_slider.setRange(0, 0)
        self._filename = None

        self._connectSignals()

    def _groupPolygons(self):
        """Open dialog to assign polygon groups."""
        text, ok = QtWidgets.QInputDialog.getMultiLineText(
            self, "Group Assigner",
            "Grouping Items:",
            "First line - Group Name\nSecond line - Group IDs (space-separated)"
        )

        if ok and text:
            lines = text.splitlines()
            for i in range(0, len(lines) - 1, 2):
                name = lines[i]
                ids = [int(x) for x in lines[i + 1].strip().split()]
                self._group_polygons[name] = ids

    def _openVideo(self):
        """Open file dialog and load video."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Video", QtCore.QDir.homePath(),
            "Video Files (*.mp4 *.avi)"
        )
        if filename:
            self._filename = os.path.splitext(os.path.basename(filename))[0]
            self._viewer.scene.loadVideo(filename)
            self._play_btn.setEnabled(True)

    def _loadROI(self):
        """Load ROI from JSON file."""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open ROI File", QtCore.QDir.homePath(),
            "JSON Files (*.json)"
        )
        if filename:
            if not self._filename:
                self._filename = os.path.splitext(os.path.basename(filename))[0]
            self._viewer.scene.loadROI(filename)

    def _save(self):
        """Save polygons and counts to JSON."""
        if not self._filename:
            return

        data = {}
        for label, (count_layout, lane_layout) in self._polygon_controls.items():
            polygon = self._viewer.scene.getPolygon(label)
            if not polygon:
                continue

            # Collect points (normalized)
            points = np.array([[p.x(), p.y()] for p in polygon._points])
            points[:, 0] /= self._viewer.scene.video_size.width()
            points[:, 1] /= self._viewer.scene.video_size.height()

            # Get count from edit field or polygon
            edit_text = count_layout.itemAt(3).widget().text()
            count = int(edit_text) if edit_text else polygon.click_count

            # Collect lane counts
            lanes = {}
            for i in range(lane_layout.count()):
                if i % 3 == 2:
                    lane_num = (i // 3) + 1
                    text = lane_layout.itemAt(i).widget().text()
                    lanes[lane_num] = int(text) if text else polygon.lane_counts.get(lane_num, 0)

            data[label + 1] = {
                'roi': points.tolist(),
                'counts': count,
                'lanes': lanes
            }

        data['group'] = self._group_polygons

        with open(f'{self._filename}.json', 'w') as f:
            json.dump(data, f, indent=2)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = VideoCountingAnnotation()
    window.resize(1920, 1080)
    window.show()
    sys.exit(app.exec())
