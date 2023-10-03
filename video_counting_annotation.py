from collections import defaultdict
from enum import Enum
from functools import partial
from PyQt6 import QtWidgets, QtGui, QtCore, QtMultimedia, QtMultimediaWidgets
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtCore import QDir, Qt, QUrl, QSizeF
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QLabel,
        QPushButton, QSizePolicy, QSlider, QStyle, QVBoxLayout, QWidget, QMainWindow)
import sys
import numpy as np
import json
import os


# Point graphics class. Can move and hover around
class GripItem(QtWidgets.QGraphicsPathItem):
    circle = QtGui.QPainterPath()
    circle.addEllipse(QtCore.QRectF(-10, -10, 20, 20))
    square = QtGui.QPainterPath()
    square.addRect(QtCore.QRectF(-15, -15, 30, 30))

    def __init__(self, annotation_item, index):
        super(GripItem, self).__init__()
        self.m_annotation_item = annotation_item
        self.m_index = index

        self.setPath(GripItem.circle)
        self.setBrush(QtGui.QColor("green"))
        self.setPen(QtGui.QPen(QtGui.QColor("green"), 2))
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(11) 
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))

    def hoverEnterEvent(self, event):
        self.setPath(GripItem.square)
        self.setBrush(QtGui.QColor("red"))
        super(GripItem, self).hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setPath(GripItem.circle)
        self.setBrush(QtGui.QColor("green"))
        super(GripItem, self).hoverLeaveEvent(event)

    def mouseReleaseEvent(self, event):
        self.setSelected(False)
        super(GripItem, self).mouseReleaseEvent(event)

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.isEnabled():
            self.m_annotation_item.movePoint(self.m_index, value)
        return super(GripItem, self).itemChange(change, value)
    
class Instructions(Enum):
    No_Instruction = 0
    Polygon_Instruction = 1
 
class PolygonAnnotation(QtWidgets.QGraphicsPolygonItem):
    def __init__(self, parent=None, main_class=None):
        super(PolygonAnnotation, self).__init__(parent)
        self.m_points = []
        self.setZValue(10)
        self.setPen(QtGui.QPen(QtGui.QColor("green"), 2))
        self.setAcceptHoverEvents(True)

        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.m_items = []
        self.num_clicks = 0
        self.position_label = None
        self.label = ''
        self.mainClass = main_class
 
    def number_of_points(self):
        return len(self.m_items)

    def addPoint(self, p):
        self.m_points.append(p)
        self.setPolygon(QtGui.QPolygonF(self.m_points))
        item = GripItem(self, len(self.m_points) - 1)
        self.scene().addItem(item)
        self.m_items.append(item)
        item.setPos(p)
        
    def removeLastPoint(self):
        if self.m_points:
            self.m_points.pop()
            self.setPolygon(QtGui.QPolygonF(self.m_points))
            it = self.m_items.pop()
            self.scene().removeItem(it)
            del it
        
    def movePoint(self, i, p):

        if 0 <= i < len(self.m_points):
            self.m_points[i] = self.mapFromScene(p)
            self.setPolygon(QtGui.QPolygonF(self.m_points))

    
    def move_item(self, index, pos):
        if 0 <= index < len(self.m_items):
            item = self.m_items[index]
            item.setEnabled(False)
            item.setPos(pos)
            item.setEnabled(True)

    def itemChange(self, change, value):
        
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for i, point in enumerate(self.m_points):
                self.move_item(i, self.mapToScene(point))
            
        return super(PolygonAnnotation, self).itemChange(change, value)

    def mousePressEvent(self, event):
        self.num_clicks += 1
        self.mainClass.setLabels()
        return super(PolygonAnnotation, self).mousePressEvent(event)
    
    def hoverEnterEvent(self, event):
        self.setBrush(QtGui.QColor(255, 0, 0, 100))
        super(PolygonAnnotation, self).hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QtGui.QBrush(QtCore.Qt.BrushStyle.NoBrush))
        super(PolygonAnnotation, self).hoverLeaveEvent(event)
 
class AnnotationScene(QtWidgets.QGraphicsScene):
    
    def __init__(self, parent=None):
        super(AnnotationScene, self).__init__(parent)

        # For video
        self.player = QtMultimedia.QMediaPlayer()
        self.video_item = QtMultimediaWidgets.QGraphicsVideoItem()
        self.video_item.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.CrossCursor))
        self.video_item.setSize(QSizeF(2560, 1440))
        self.player.setVideoOutput(self.video_item)
        self.addItem(self.video_item)
        
        self.mainClass = parent

        self.current_instruction = Instructions.No_Instruction
        self.polygon_item = None
        self.num_polygons = 0
        self.clicks_inside_polygon = dict()
        self.polygons = list()
        self.polygon_labels = list()

    def load_video(self, filename):
        
        self.player.setSource(QUrl.fromLocalFile(filename))
        self.setSceneRect(self.video_item.boundingRect())

    def deleteLastPolygon(self):
        
        if len(self.polygons) > 0:
            for item in self.polygons[-1].m_items:
                self.removeItem(item)
        
            self.removeItem(self.polygons[-1])
            self.removeItem(self.polygon_labels[-1])
            self.num_polygons -= 1
            del self.polygons[-1]
            del self.polygon_labels[-1]
        
    def setCurrentInstruction(self, instruction):
        
        if instruction == Instructions.No_Instruction and self.polygon_item is not None:
            self.polygon_item.removeLastPoint()
            
            pt = self.addText(str(self.num_polygons), QtGui.QFont('Arial', 40, QtGui.QFont.Weight.Bold))
            pt.setDefaultTextColor(QtGui.QColor(255, 0, 0))
            
            points = np.empty(shape=(0, 2))
            for point in self.polygon_item.m_points:
                p = (point.x(), point.y())
                points = np.vstack((points, p))
            
            mean = np.mean(points, axis=0)
            pt.setPos(mean[0], mean[1])
            self.polygon_item.position_label = pt
            self.polygons.append(self.polygon_item)
            self.polygon_labels.append(pt)
            self.mainClass.addButtonsAndLabels(self.polygon_item.label)
        
        self.current_instruction = instruction
        self.polygon_item = None
        if self.current_instruction == Instructions.Polygon_Instruction:
            self.polygon_item = PolygonAnnotation(main_class=self.mainClass)
            self.polygon_item.label = self.num_polygons
            self.addItem(self.polygon_item)
            self.clicks_inside_polygon[self.num_polygons] = self.polygon_item
            self.num_polygons += 1
            
    def mousePressEvent(self, event):
        
        if self.current_instruction == Instructions.Polygon_Instruction and event.button() == Qt.MouseButton.LeftButton:
            self.polygon_item.removeLastPoint()
            self.polygon_item.addPoint(event.scenePos())
            self.polygon_item.addPoint(event.scenePos())
            
        super(AnnotationScene, self).mousePressEvent(event)
        
    def mouseMoveEvent(self, event):
        if self.current_instruction == Instructions.Polygon_Instruction:
            self.polygon_item.movePoint(self.polygon_item.number_of_points()-1, event.scenePos())
        super(AnnotationScene, self).mouseMoveEvent(event)

class QtPolygonViewer(QtWidgets.QGraphicsView):

    rightMouseButtonPressed = pyqtSignal(float, float)
    rightMouseButtonReleased = pyqtSignal(float, float)
    rightMouseButtonDoubleClicked = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super(QtPolygonViewer, self).__init__(parent)
        
        self.setRenderHints(QtGui.QPainter.RenderHint.Antialiasing | QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        self.setMouseTracking(True)    
        self.zoomStack = list()    
        self.aspectRatioMode = Qt.AspectRatioMode.KeepAspectRatio
        self.scene = AnnotationScene(parent)
        self.setScene(self.scene)
        
        self.fitInView(self.scene.video_item, Qt.AspectRatioMode.KeepAspectRatio)
    
    def updateViewer(self):
    
        if len(self.zoomStack) and self.sceneRect().contains(self.zoomStack[-1]):
            self.fitInView(self.zoomStack[-1], Qt.AspectRatioMode.IgnoreAspectRatio)  # Show zoomed rect (ignore aspect ratio).
        else:
            self.zoomStack = []  # Clear the zoom stack (in case we got here because of an invalid zoom).
            self.fitInView(self.sceneRect(), self.aspectRatioMode)  # Show entire image (use current aspect ratio mode).
   
    def mousePressEvent(self, event):
        
        if event.button() == Qt.MouseButton.RightButton:
            
            scenePos = self.mapToScene(event.pos())
            self.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
            self.rightMouseButtonPressed.emit(scenePos.x(), scenePos.y())
        
        super(QtPolygonViewer, self).mousePressEvent(event)
        
    def mouseReleaseEvent(self, event):
        
        super(QtPolygonViewer, self).mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.RightButton:
            scenePos = self.mapToScene(event.pos())
            viewBBox = self.zoomStack[-1] if len(self.zoomStack) else self.sceneRect()
            selectionBBox = self.scene.selectionArea().boundingRect().intersected(viewBBox)
            self.scene.setSelectionArea(QtGui.QPainterPath())  # Clear current selection area.
            if selectionBBox.isValid() and (selectionBBox != viewBBox):
                self.zoomStack.append(selectionBBox)
                self.updateViewer()
            self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
            self.rightMouseButtonReleased.emit(scenePos.x(), scenePos.y())
    
    def resizeEvent(self, event):
        self.updateViewer()
        
    def mouseDoubleClickEvent(self, event):
        
        scenePos = self.mapToScene(event.pos())
        if event.button() == Qt.MouseButton.RightButton:
            self.zoomStack = []  # Clear zoom stack.
            self.updateViewer()
            self.rightMouseButtonDoubleClicked.emit(scenePos.x(), scenePos.y())
        
        QtWidgets.QGraphicsView.mouseDoubleClickEvent(self, event)

    # def resizeEvent(self, event):
    #     super().resizeEvent(event)
    #     self.fitInView(self.scene.video_item, Qt.AspectRatioMode.KeepAspectRatio)

class VideoCountingAnnotation(QMainWindow):
    
    def __init__(self, parent=None):
        super(VideoCountingAnnotation, self).__init__(parent=parent)
        self.setWindowTitle('Counting Annotation Tool')
        
        self.annotationView = QtPolygonViewer(self)
        
        QtGui.QShortcut(QtCore.Qt.Key.Key_Escape, self, activated=partial(self.annotationView.scene.setCurrentInstruction, Instructions.No_Instruction))
        QtGui.QShortcut(QtCore.Qt.Key.Key_Space, self, activated=self.actionPlayVideo)
        QtGui.QShortcut(QtCore.Qt.Key.Key_Right, self, activated=self.actionForwardVideo)
        QtGui.QShortcut(QtCore.Qt.Key.Key_Left, self, activated=self.actionBackwardVideo)
        
        self.buttons_and_labels = defaultdict(list)
        self.filename = 'roi'
        self.fowrwad_milliseconds = 1000
        
        # Add menubar for loading the video and exiting the application
        menuBar = self.menuBar()
        menuOpen = QAction(QIcon('open.png'), '&Open Video', self)       
        menuOpen.setShortcut('Ctrl+O')
        menuOpen.setStatusTip('Open video')
        menuOpen.triggered.connect(self.actionOpenFile)

        menuExit = QAction(QIcon('exit.png'), '&Exit', self)        
        menuExit.setShortcut('Ctrl+Q')
        menuExit.setStatusTip('Exit application')
        menuExit.triggered.connect(self.actionExitApp)
        
        menuDrawPolygon = QAction('Draw Polygon', self)
        menuDrawPolygon.setShortcut('Ctrl+D')
        menuDrawPolygon.setStatusTip('Draw polygon')
        menuDrawPolygon.triggered.connect(partial(self.annotationView.scene.setCurrentInstruction, Instructions.Polygon_Instruction))
       
        menuSavePolygon = QAction('Save Polygon', self)
        menuSavePolygon.setShortcut('Ctrl+S')
        menuSavePolygon.setStatusTip('Save polygon')
        menuSavePolygon.triggered.connect(self.actionSavePolygon)
        
        fileMenu = menuBar.addMenu('File')
        fileMenu.addAction(menuOpen)
        fileMenu.addAction(menuExit)
        controlMenu = menuBar.addMenu('Controls')
        controlMenu.addAction(menuDrawPolygon)
        controlMenu.addAction(menuSavePolygon)
        
        # Add necessary buttons
        self.playButton = QPushButton()
        self.playButton.setEnabled(False)
        self.playButton.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.playButton.clicked.connect(self.actionPlayVideo)

        self.deleteLastPolygonButton = QPushButton()
        self.deleteLastPolygonButton.setText('Delete Last Polygon')
        self.deleteLastPolygonButton.clicked.connect(self.actionDeleteLastPolygon)
        self.savePolygonButton = QPushButton()
        self.savePolygonButton.setText('Save Progress')
        self.savePolygonButton.clicked.connect(self.actionSavePolygon)
        self.loadROIButton = QPushButton()
        self.loadROIButton.setText('Load ROI')
        self.loadROIButton.clicked.connect(self.actionLoadROI)
        
        self.positionSlider = QSlider(Qt.Orientation.Horizontal)
        self.positionSlider.setRange(0, 0)
        self.positionSlider.sliderMoved.connect(self.actionSetPosition)
        self.labelTimer = QLabel()
        self.labelTimer.setText('00:00:00/00:00:00')

        self.errorLabel = QLabel()
        self.errorLabel.setSizePolicy(QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Maximum)
        
        wid = QWidget()
        self.setCentralWidget(wid)
        
        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.setContentsMargins(0, 0, 0, 0)
        self.buttonLayout.addWidget(self.deleteLastPolygonButton)
        self.buttonLayout.addWidget(self.savePolygonButton)
        
        controlLayout = QHBoxLayout()
        controlLayout.setContentsMargins(0, 0, 0, 0)
        controlLayout.addWidget(self.playButton)
        controlLayout.addWidget(self.positionSlider)
        controlLayout.addWidget(self.labelTimer)

        layout = QVBoxLayout()
        layout.addWidget(self.annotationView)
        layout.addLayout(controlLayout)
        layout.addLayout(self.buttonLayout)
        
        wid.setLayout(layout)
        
        self.annotationView.scene.player.playbackStateChanged.connect(self.actionMediaStateChanged)
        self.annotationView.scene.player.positionChanged.connect(self.actionPositionChanged)
        self.annotationView.scene.player.durationChanged.connect(self.actionDurationChanged)
        self.annotationView.scene.player.errorOccurred.connect(self.actionHandleError)
    
    def setLabels(self):
        
        for label, ls in self.buttons_and_labels.items():
            ls[2].setText(str(self.annotationView.scene.clicks_inside_polygon[label].num_clicks))
    
    def actionLoadROI(self):
        
        pass
        
    def actionSavePolygon(self):
        
        roi_dict = defaultdict(dict)
        for label, polygon in self.annotationView.scene.clicks_inside_polygon.items():
            points = np.empty(shape=(0, 2))
            for point in polygon.m_points:
                p = (point.x(), point.y())
                points = np.vstack((points, p))

            # Save normalized coordinates
            points[:, 0] /= self.annotationView.scene.video_item.size().width()
            points[:, 1] /= self.annotationView.scene.video_item.size().height()
            
            roi_dict[label]['roi'] = points.tolist()
            roi_dict[label]['counts'] = polygon.num_clicks
        
        with open(f'{self.filename}.json', 'w') as f:
            json.dump(roi_dict, f)
        
    def addButtonsAndLabels(self, label):
        
        deleteLastCountButton = QPushButton()
        deleteLastCountButton.setText(f'Delete Last Count P{label}')
        
        deleteLastCountButton.clicked.connect(partial(self.deleteLastCount, label))
        
        self.buttons_and_labels[label].append(deleteLastCountButton)
        countLabel = QLabel()
        countLabel.setText(f'PC{label}: ')
        countLabelNo = QLabel()
        countLabelNo.setText('')
        
        self.buttons_and_labels[label].append(countLabel)
        self.buttons_and_labels[label].append(countLabelNo)
        self.buttonLayout.addWidget(deleteLastCountButton)
        self.buttonLayout.addWidget(countLabel)
        self.buttonLayout.addWidget(countLabelNo)
        
        self.last_added_label = label
        
    def deleteLastCount(self, label):

        self.annotationView.scene.clicks_inside_polygon[label].num_clicks -= 1
        self.setLabels()
    
    def actionDeleteLastPolygon(self):
        
        if len(self.buttons_and_labels) > 0:
            self.annotationView.scene.deleteLastPolygon()
            last_key = list(self.buttons_and_labels.keys())[-1]
            self.buttons_and_labels[last_key][0].deleteLater()
            self.buttons_and_labels[last_key][1].deleteLater()
            self.buttons_and_labels[last_key][2].deleteLater()
            
            del self.buttons_and_labels[last_key]

    def actionForwardVideo(self):
        curr_position = self.annotationView.scene.player.position()
        next_position = min(curr_position + self.fowrwad_milliseconds, self.annotationView.scene.player.duration())
        self.annotationView.scene.player.setPosition(next_position)
        
    def actionBackwardVideo(self):
        curr_position = self.annotationView.scene.player.position()
        next_position = max(0, curr_position - self.fowrwad_milliseconds)
        self.annotationView.scene.player.setPosition(next_position)
    
    def getSecondsFormat(self, milliseconds):
        
        seconds = milliseconds / 1000
        (hours, seconds) = divmod(seconds, 3600)
        (minutes, seconds) = divmod(seconds, 60)
        formatted = f"{hours:02.0f}:{minutes:02.0f}:{seconds:05.2f}"
        return formatted
        
    def actionPositionChanged(self, position):
        self.positionSlider.setValue(position)

        total_seconds = self.annotationView.scene.player.duration()
        position_format = self.getSecondsFormat(position)
        total_format = self.getSecondsFormat(total_seconds)
        self.labelTimer.setText(f'{position_format} / {total_format}')
    
    def actionDurationChanged(self, duration):
        self.positionSlider.setRange(0, duration)
    
    def actionHandleError(self):
        self.playButton.setEnabled(False)
        self.errorLabel.setText("Error: " + self.annotationView.scene.player.errorString())
    
    def actionMediaStateChanged(self):

        if self.annotationView.scene.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.playButton.setIcon(
                    self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        else:
            self.playButton.setIcon(
                    self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
    
    def actionSetPosition(self, position):
        self.annotationView.scene.player.setPosition(position)
        
    def actionOpenFile(self):
        
        fileName, _ = QFileDialog.getOpenFileName(self, "Open Video",
                QDir.homePath())
        self.filename = os.path.splitext(os.path.basename(fileName))[0]
        
        self.annotationView.scene.load_video(fileName)
        
        self.playButton.setEnabled(True)

    def actionPlayVideo(self):
        
        if self.annotationView.scene.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.annotationView.scene.player.pause()
        else:
            self.annotationView.scene.player.play()
    
    def actionExitApp(self):
        sys.exit(0)
    
if __name__ == '__main__':
    
    
    app = QApplication(sys.argv)
    player = VideoCountingAnnotation()
    player.resize(1920, 1080)
    player.show()
    sys.exit(app.exec())