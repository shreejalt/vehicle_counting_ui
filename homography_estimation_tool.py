from enum import Enum
from functools import partial
from PyQt6 import QtWidgets, QtGui, QtCore, QtMultimedia, QtMultimediaWidgets
from PyQt6.QtCore import pyqtSignal, Qt, QSizeF, QUrl
from PyQt6.QtWidgets import (QHBoxLayout, QPushButton, QVBoxLayout, QWidget, QMessageBox)
from PyQt6.QtMultimedia import QMediaPlayer
import cv2
import numpy as np
from collections import defaultdict
import os
import json
import rasterio

# Import the Matlab engine if installed
try:
    import matlab.engine
    eng = matlab.engine.start_matlab()
except ImportError:
    print('Matlab engine is not installed in the environment..skipping.')


def convert_cv_qt(cv_img, rgb=False):
    """
    Convert a OpenCV image to a Qt pixmap.
    Args:
        cv_img (numpy.ndarray): The OpenCV image to be converted.
        rgb (bool, optional): Flag indicating whether the image is in RGB format. 
                              Defaults to False.
    Returns:
        QtGui.QPixmap: The converted Qt pixmap.
    """
    
    rgb_image = cv_img
    if not rgb:
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        
    h, w, ch = rgb_image.shape
    bytes_per_line = ch * w

    convert_to_Qt_format = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
    p = convert_to_Qt_format.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio)
    return QtGui.QPixmap.fromImage(p)

def pixel_to_utm(px, transform_matrix):
    """
    Converts pixel coordinates to UTM coordinates using a given transformation matrix.
    Args:
        px (tuple): A tuple containing the pixel coordinates (row, column).
        transform_matrix (numpy.ndarray): The transformation matrix used to convert pixel coordinates to UTM coordinates.
    Returns:
        tuple: A tuple containing the UTM coordinates (utm_x, utm_y).
    """
    utm_x, utm_y = rasterio.transform.xy(transform_matrix, px[1], px[0])
    return utm_x, utm_y

class Instructions(Enum):
    No_Instruction = 0
    Point_Instruction = 1
    Polygon_Instruction = 2

class ImagePopup(QtWidgets.QDialog):
    
    """
    A dialog window for displaying images.
    Args:
        parent: The parent widget of the dialog.
    Attributes:
        label_warped (QtWidgets.QLabel): QLabel widget for displaying the warped image.
        label_reprojected (QtWidgets.QLabel): QLabel widget for displaying the reprojected image.
        layout (QtWidgets.QVBoxLayout): QVBoxLayout for arranging the image labels.
    Methods:
        __init__(self, parent): Initializes the ImagePopup dialog.
        setImage(self, img, reproject=False): Sets the image to be displayed in the dialog.
        resetImage(self): Clears the displayed images in the dialog.
    """
    
    def __init__(self, parent):
        super().__init__(parent)
        
        self.setWindowTitle('Homography Image')
        self.label_warped = QtWidgets.QLabel(self)
        self.label_reprojected = QtWidgets.QLabel(self)
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.label_warped)
        self.layout.addWidget(self.label_reprojected)
        self.setLayout(self.layout)
        # self.adjustSize()
    
    def setImage(self, img, reproject=False):
        cv2.imwrite('result_reprojection.jpg', img)
        pix_img = convert_cv_qt(img)
        if reproject:
            self.label_reprojected.setPixmap(pix_img)
        else:
            self.label_warped.setPixmap(pix_img)
    
    def resetImage(self):
        self.label_warped.clear()
        self.label_reprojected.clear()
        
class GripItem(QtWidgets.QGraphicsPathItem):
    """
    A custom QGraphicsPathItem representing a moving point for annotation items.
    Args:
        annotation_item (QtWidgets.QGraphicsItem): The parent annotation item.
        id (int, optional): The ID of the grip item. Defaults to 0.
        polygon_id (int, optional): The ID of the polygon. Defaults to 0.
    Attributes:
        circle (QtGui.QPainterPath): The path representing a circle shape.
        square (QtGui.QPainterPath): The path representing a square shape.
        annotation_item (QtWidgets.QGraphicsItem): The parent annotation item.
        id (int): The ID of the grip item.
        polygon_id (int): The ID of the polygon.
        set (bool): Flag indicating if the grip item is set.
    Methods:
        hoverEnterEvent(event): Event handler for hover enter event.
        hoverLeaveEvent(event): Event handler for hover leave event.
        mouseReleaseEvent(event): Event handler for mouse release event.
        itemChange(change, value): Event handler for item change event.
    """
    
    circle = QtGui.QPainterPath()
    circle.addEllipse(QtCore.QRectF(-10, -10, 20, 20))
    square = QtGui.QPainterPath()
    square.addRect(QtCore.QRectF(-15, -15, 30, 30)) 
    
    def __init__(self, annotation_item, id=0, polygon_id=0):
        super(GripItem, self).__init__()
        
        self.annotation_item = annotation_item
        self.id = id
        self.polygon_id = polygon_id
        self.set = False
        
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
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.isEnabled():
            self.annotation_item.movePoint(self.id, value)
            
            if isinstance(self.annotation_item, PolygonAnnotation):
                if self.annotation_item.calling_class.is_ground_plane:
                    pos_image = self.annotation_item.calling_class.convertToNumpy(value)
                    reproj_point = self.annotation_item.calling_class.viewer.getReReprojectedPoints(pos_image)
                    pos_image_pyqt = self.annotation_item.calling_class.convertToPyQt(reproj_point[0])
                    if self.polygon_id in self.annotation_item.calling_class.viewer.imagePlane.scene.polygon_items:
                        self.annotation_item.calling_class.viewer.imagePlane.scene.polygon_items[self.polygon_id].movePoint(self.id, pos_image_pyqt)
                        self.annotation_item.calling_class.viewer.imagePlane.scene.polygon_items[self.polygon_id].setItemPos(self.id, pos_image_pyqt)                     
                else:
                    pos_ground = self.annotation_item.calling_class.convertToNumpy(value)
                    reproj_point = self.annotation_item.calling_class.viewer.getReprojectedPoints(pos_ground)
                    pos_ground_pyqt = self.annotation_item.calling_class.convertToPyQt(reproj_point[0])
                    if self.polygon_id in self.annotation_item.calling_class.viewer.groundPlane.scene.polygon_items:
                        self.annotation_item.calling_class.viewer.groundPlane.scene.polygon_items[self.polygon_id].movePoint(self.id, pos_ground_pyqt)
                        self.annotation_item.calling_class.viewer.groundPlane.scene.polygon_items[self.polygon_id].setItemPos(self.id, pos_ground_pyqt)
            
        return super(GripItem, self).itemChange(change, value)

class PointAnnotation(QtWidgets.QGraphicsItem):
    """
    A class representing a point annotation in a graphics item.
    Attributes:
        coords (QtWidgets.QGraphicsTextItem): The text item displaying the coordinates of the point.
        point (GripItem): The grip item representing the point.
        parent: The parent item of the point annotation.
        set (bool): Indicates whether the point has been set or not.
        utm_coords: The UTM coordinates of the point.
    Properties:
        points (tuple): The x and y coordinates of the point.
        utm_points (list): The UTM coordinates of the point.
    Methods:
        setPoint(p, id): Sets the point and displays its ID.
        movePoint(id, pos): Moves the point to the specified position and updates its ID.
    """
    def __init__(self, parent=None):
        super(PointAnnotation, self).__init__()
        self.setZValue(10)
        self.setAcceptHoverEvents(True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.coords = QtWidgets.QGraphicsTextItem('', self)
        self.coords.setDefaultTextColor(QtGui.QColor(0, 255, 0))
        self.coords.setPos(0, 0)
        self.coords.setFont(QtGui.QFont('Arial', 10, QtGui.QFont.Weight.Bold))
        self.point = None
        self.parent = parent
        self.set = False
        self.utm_coords = None
        
    @property
    def points(self):
        return (self.point.x(), self.point.y())
    
    @property
    def utm_points(self):
        
        if self.utm_coords is not None:
            return self.utm_coords
        else:
            return []
    
    def setPoint(self, p, id):
        
        self.c = self.mapFromScene(p)
        self.point = GripItem(self, id)
        self.scene().addItem(self.point)
        self.point.setPos(self.c)
        self.coords.setPlainText(f'ID: {id}')
        self.coords.setPos(self.c)

    def movePoint(self, id, pos):
            
        self.c = self.mapFromScene(pos)
        self.point.setPos(self.c)
        self.coords.setPos(self.c)
        self.coords.setPlainText(f'ID: {id}')

class PolygonAnnotation(QtWidgets.QGraphicsPolygonItem):
    
    """
    A custom QGraphicsPolygonItem subclass for polygon annotation.
    Attributes:
        items (list): A list of GripItem objects representing the control points of the polygon.
        points (list): A list of QPointF objects representing the vertices of the polygon.
        label (str): The label associated with the polygon.
        calling_class: The calling class object.
        id: A QGraphicsTextItem object representing the ID of the polygon.
    Methods:
        numPoints(): Returns the number of control points in the polygon.
        polypoints(): Returns the vertices of the polygon as a numpy array.
        getPoints(): Returns the mean position of the control points.
        moveLabel(): Moves the ID label to the mean position of the control points.
        addPoint(p): Adds a control point to the polygon.
        setItemPos(i, pos): Sets the position of a control point.
        removeLastPoint(): Removes the last control point from the polygon.
        movePoint(i, p): Moves a control point to a new position.
        move_item(index, pos): Moves a control point item to a new position.
        itemChange(change, value): Overrides the itemChange method to handle control point movement.
        hoverEnterEvent(event): Overrides the hoverEnterEvent method to handle hover enter event.
        hoverLeaveEvent(event): Overrides the hoverLeaveEvent method to handle hover leave event.
    
    """
    
    def __init__(self, parent=None, calling_class=None):
        super(PolygonAnnotation, self).__init__(parent)
        
        self.setZValue(10)
        self.setPen(QtGui.QPen(QtGui.QColor("green"), 2))
        self.setAcceptHoverEvents(True)

        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
                
        self.items = []
        self.points = []
        self.label = ''
        self.calling_class = calling_class
        self.id = QtWidgets.QGraphicsTextItem('', self)
        self.id.setDefaultTextColor(QtGui.QColor(0, 255, 0))
        self.id.setPos(0, 0)
        self.id.setFont(QtGui.QFont('Arial', 20, QtGui.QFont.Weight.Bold))
        
    def numPoints(self):
        return len(self.items)
 
    @property
    def polypoints(self):
        
        points = np.empty(shape=(0, 2))
        for point in self.points:
            p = (point.x(), point.y())
            points = np.vstack((points, p))
        return points

    def getPoints(self):
        
        points = np.empty(shape=(0, 2))
        for point in self.points:
            p = (point.x(), point.y())
            points = np.vstack((points, p))
        mean = np.mean(points, axis=0)
        return mean
    
    def moveLabel(self):
        
        mean_pos = self.getPoints()
        self.id.setPos(QtCore.QPointF(mean_pos[0], mean_pos[1]))
        self.id.setPlainText(str(self.label + 1))

    def addPoint(self, p):
        self.points.append(p)
        self.setPolygon(QtGui.QPolygonF(self.points))
        item = GripItem(self, len(self.points) - 1, polygon_id=self.label)
        self.scene().addItem(item)
        self.items.append(item)
        item.setPos(p)
    
    def setItemPos(self, i, pos):
        if 0 <= i < len(self.items):
            self.items[i].setPos(pos)
    
    def removeLastPoint(self):
        if self.points:
            self.points.pop()
            self.setPolygon(QtGui.QPolygonF(self.points))
            it = self.items.pop()
            self.scene().removeItem(it) 
            del it
        
    def movePoint(self, i, p):
        if 0 <= i < len(self.points):
            self.points[i] = self.mapFromScene(p)
            self.setPolygon(QtGui.QPolygonF(self.points))
            self.moveLabel()
            
    def move_item(self, index, pos):
        if 0 <= index < len(self.items):
            item = self.items[index]
            item.setEnabled(False)
            item.setPos(pos)
            item.setEnabled(True)
    
    def itemChange(self, change, value):
    
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for i, point in enumerate(self.points):
                new_point = self.mapToScene(point)
                self.move_item(i, new_point)
           
        return super(PolygonAnnotation, self).itemChange(change, value)
    
    def hoverEnterEvent(self, event):
        self.setBrush(QtGui.QColor(255, 0, 0, 100))
        super(PolygonAnnotation, self).hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QtGui.QBrush(QtCore.Qt.BrushStyle.NoBrush))
        super(PolygonAnnotation, self).hoverLeaveEvent(event)
 
class HomographyScene(QtWidgets.QGraphicsScene):
    """
    A QGraphicsScene subclass for handling homography estimation and annotation in a graphical scene.
    Args:
        parent (QWidget): The parent widget.
        is_ground_plane (bool): Flag indicating if the scene represents the ground plane.
        show_utm (bool): Flag indicating if UTM coordinates should be shown.
    Attributes:
        viewer (QWidget): The parent widget.
        is_ground_plane (bool): Flag indicating if the scene represents the ground plane.
        show_utm (bool): Flag indicating if UTM coordinates should be shown.
        file_loaded (bool): Flag indicating if a file has been loaded.
        image_item (QGraphicsPixmapItem): The item for displaying an image.
        current_instruction (Instructions): The current instruction for annotation.
        player (QMediaPlayer): The media player for playing videos.
        video_item (QGraphicsVideoItem): The item for displaying a video.
        point_item (PointAnnotation): The current point annotation item.
        polygon_item (PolygonAnnotation): The current polygon annotation item.
        instruction (Instructions): The current instruction for annotation.
        current_mouse_coords (QGraphicsTextItem): The item for displaying current mouse coordinates.
        point_items (defaultdict): Dictionary for storing point annotation items.
        polygon_items (defaultdict): Dictionary for storing polygon annotation items.
        reprojected_polygons (defaultdict): Dictionary for storing reprojected polygons.
        point_id (int): The ID for the next point annotation.
        polygon_id (int): The ID for the next polygon annotation.
        reprojected_polygon_id (int): The ID for the next reprojected polygon.
        image_width (int): The width of the loaded image.
        image_height (int): The height of the loaded image.
        orthophoto_set (bool): Flag indicating if an orthophoto has been set.
        utm (bool): Flag indicating if UTM coordinates should be shown.
        item_loaded (str): The type of item loaded ('image' or 'video').
        image_filename (str): The filename of the loaded image.
        ground_orthophoto (rasterio.DatasetReader): The orthophoto dataset for the ground plane.
        transform_matrix (affine.Affine): The transformation matrix for the orthophoto.
    Methods:
        set_default(): Set default values for the scene.
        load_points(points): Load point annotations into the scene.
        load_utm_points(points): Load UTM coordinates for point annotations.
        load_image(filename): Load an image or video into the scene.
        setCurrentInstruction(instruction, dont_recurse=False): Set the current annotation instruction.
        deleteLastPoint(): Delete the last point annotation.
        deleteLastPolygon(dont_recurse=False): Delete the last polygon annotation.
        loadROI(filename): Load regions of interest (ROIs) from a file.
    """
    
    def __init__(self, parent=None, is_ground_plane=False, show_utm=False):
        
        super(HomographyScene, self).__init__(parent)
        
        self.viewer = parent
        self.is_ground_plane = is_ground_plane
        self.show_utm = show_utm
        self.file_loaded = False
        self.set_default()
    
    def set_default(self):
        
        # For image
        self.image_item = QtWidgets.QGraphicsPixmapItem()
        self.image_item.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.CrossCursor))
        self.current_instruction = Instructions.No_Instruction
        
        # For video
        self.player = QtMultimedia.QMediaPlayer()
        self.video_item = QtMultimediaWidgets.QGraphicsVideoItem()
        self.video_item.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.CrossCursor))
        self.video_item.setSize(QSizeF(3840, 2160))
        self.player.setVideoOutput(self.video_item)
        
        self.point_item = None
        self.polygon_item = None
        self.roi = None
        self.instruction = Instructions.No_Instruction
        self.current_mouse_coords = None
       
        self.point_items = defaultdict()
        self.polygon_items = defaultdict()
        self.reprojected_polygons = defaultdict()
        
        self.point_id = 0
        self.polygon_id = 0
        self.reprojected_polygon_id = 0
        self.image_width, self.image_height = None, None
        self.orthophoto_set = False
        self.utm = False
        self.item_loaded = None
        
    def load_points(self, points):
        
        for p in points:
            self.point_item = PointAnnotation()
            self.addItem(self.point_item)
            self.point_item.setPoint(QtCore.QPointF(p[0], p[1]), self.point_id)
            self.point_item.set = True
            self.point_items[self.point_id] = self.point_item
            self.point_id += 1
            self.point_item = None

    def load_utm_points(self, points):
        
        for point_id in self.point_items.keys():
            self.point_items[point_id].utm_coords = points[point_id]
    
    def load_image(self, filename):
        
        if self.is_ground_plane and (('tif' in filename) or ('img' in filename)):
            
            orthophoto = rasterio.open(filename)
            red, green, blue = orthophoto.read(1), orthophoto.read(2), orthophoto.read(3)
            cv_img = np.dstack((red, green, blue))
            if orthophoto.count > 4:
                self.elevation_map = orthophoto.read(5)
            qt_img = convert_cv_qt(cv_img, rgb=True)
            self.image_item.setPixmap(qt_img)
            self.ground_orthophoto = orthophoto
            self.orthophoto_set = True
            self.utm = self.show_utm and self.orthophoto_set
            self.transform_matrix = orthophoto.transform
            self.addItem(self.image_item)
            self.setSceneRect(self.image_item.boundingRect())
            self.item_loaded = 'image'
            
        elif (('jpg' in filename) or ('png' in filename)):
            self.image_item.setPixmap(QtGui.QPixmap(filename))
            self.addItem(self.image_item)
            self.setSceneRect(self.image_item.boundingRect())
            self.item_loaded = 'image'
            
        elif ('mp4' in filename):
            self.player.setSource(QUrl.fromLocalFile(filename))
            self.addItem(self.video_item)
            self.setSceneRect(self.video_item.boundingRect())
            self.item_loaded = 'video'
            
        self.image_filename = filename
        self.image_height, self.image_width = self.height(), self.width()
        self.current_mouse_coords = self.addText('', QtGui.QFont('Arial', 30, QtGui.QFont.Weight.Bold))
        self.current_mouse_coords.setDefaultTextColor(QtGui.QColor(255, 0, 0))
        self.current_mouse_coords.setPos(0, 0)
        self.file_loaded = True
        
    def setCurrentInstruction(self, instruction, dont_recurse=False):
        
        if instruction == Instructions.No_Instruction and self.point_item is not None:
            self.point_items[self.point_id - 1] = self.point_item
            self.point_item = None
        
        elif instruction == Instructions.Point_Instruction and self.point_item is None:
            self.point_item = PointAnnotation()
            self.addItem(self.point_item)
            self.point_id += 1
            
        elif instruction == Instructions.Polygon_Instruction and self.polygon_item is None and self.viewer.homMatrix is not None:
            
            self.polygon_item = PolygonAnnotation(calling_class=self)
            self.addItem(self.polygon_item)
            self.polygon_item.label = self.polygon_id
            self.polygon_id += 1
            if not dont_recurse:                
                if self.is_ground_plane:
                    self.viewer.imagePlane.scene.setCurrentInstruction(instruction, dont_recurse=True)
                else:
                    self.viewer.groundPlane.scene.setCurrentInstruction(instruction, dont_recurse=True)
                
        elif instruction == Instructions.No_Instruction and self.polygon_item is not None and self.viewer.homMatrix is not None:
            
            self.polygon_item.removeLastPoint()
            self.polygon_items[self.polygon_id - 1] = self.polygon_item
            self.polygon_item.moveLabel()
            self.polygon_item = None
            self.current_instruction = instruction
          
            if not dont_recurse:
                if self.is_ground_plane:
                    self.viewer.imagePlane.scene.setCurrentInstruction(instruction, dont_recurse=True)
                else:
                    self.viewer.groundPlane.scene.setCurrentInstruction(instruction, dont_recurse=True)

        self.current_instruction = instruction
        
        for point_id in self.point_items:
            self.point_items[point_id].point.show()
            self.point_items[point_id].coords.show()

    def deleteLastPoint(self):
        
        if len(self.point_items.keys()) > 0:
            self.point_id -= 1
            self.removeItem(self.point_items[self.point_id].point)
            self.removeItem(self.point_items[self.point_id])
            del self.point_items[self.point_id]

    def deleteLastPolygon(self, dont_recurse=False):
        
        if len(self.polygon_items.keys()) > 0:
            self.polygon_id -= 1
            for item in self.polygon_items[self.polygon_id].items:
                self.removeItem(item)
            self.removeItem(self.polygon_items[self.polygon_id])
            del self.polygon_items[self.polygon_id]
            if not dont_recurse:
                if self.is_ground_plane:
                    self.viewer.imagePlane.scene.deleteLastPolygon(dont_recurse=True)
                else:
                    self.viewer.groundPlane.scene.deleteLastPolygon(dont_recurse=True)

    def load_roi(self, filename):        
        with open(filename, 'r') as f:
            rois = json.load(f)
            self.roi = rois
        if self.viewer.homMatrix is not None:
            for key in rois.keys():
                if key != 'group':
                    points = np.array(rois[key]['roi'])
                    points[:, 0] *= self.image_width
                    points[:, 1] *= self.image_height
                    self.polygon_item = PolygonAnnotation(calling_class=self)
                    self.polygon_item.label = self.polygon_id
                    self.addItem(self.polygon_item)
                    if not self.is_ground_plane:
                        self.viewer.groundPlane.scene.polygon_item = PolygonAnnotation(calling_class=self.viewer.groundPlane.scene)
                        self.viewer.groundPlane.scene.polygon_item.label = self.polygon_id
                        self.viewer.groundPlane.scene.addItem(self.viewer.groundPlane.scene.polygon_item)
                 
                    for p in points:
                        
                        self.polygon_item.removeLastPoint()
                        self.polygon_item.addPoint(self.convertToPyQt(p))
                        self.polygon_item.addPoint(self.convertToPyQt(p))
                        
                        if not self.is_ground_plane:
                            
                            pos_ground = self.convertToNumpy(self.convertToPyQt(p))
                            reproj_point = self.viewer.getReprojectedPoints(pos_ground)
                            pos_ground_pyqt = self.convertToPyQt(reproj_point[0])
                            self.viewer.groundPlane.scene.polygon_item.removeLastPoint()
                            self.viewer.groundPlane.scene.polygon_item.addPoint(pos_ground_pyqt)
                            self.viewer.groundPlane.scene.polygon_item.addPoint(pos_ground_pyqt)
                        
                    self.polygon_item.removeLastPoint()
                    self.polygon_items[self.polygon_id] = self.polygon_item
                    self.polygon_item.moveLabel()
                    self.polygon_id += 1
                    
                    if not self.is_ground_plane:
                        self.viewer.groundPlane.scene.polygon_item.removeLastPoint()
                        self.viewer.groundPlane.scene.polygon_items[self.viewer.groundPlane.scene.polygon_id] = self.viewer.groundPlane.scene.polygon_item
                        self.viewer.groundPlane.scene.polygon_item.moveLabel()
                        
                        self.viewer.groundPlane.scene.polygon_id += 1
    
            self.polygon_item = None
            if not self.is_ground_plane:
                self.viewer.groundPlane.scene.polygon_item = None

        else:
            print('Cant load the ROI without setting the homography matrix')
    
    def mousePressEvent(self, event):
        
        if self.current_instruction == Instructions.Point_Instruction and event.button() == Qt.MouseButton.LeftButton:
            if self.point_item.point is None:
                self.point_item.setPoint(event.scenePos(), self.point_id - 1)
                self.point_item.set = True
                if self.utm:
                    x, y = tuple(map(int, self.point_item.points))
                    utm_x, utm_y = pixel_to_utm((x, y), self.transform_matrix)
                    elevation = self.elevation_map[y, x]
                    self.point_item.utm_coords = [utm_x, utm_y, elevation]
                self.setCurrentInstruction(Instructions.No_Instruction)
        
        elif self.current_instruction == Instructions.Polygon_Instruction and event.button() == Qt.MouseButton.LeftButton and self.viewer.homMatrix is not None:

            # Hide all the point items when polygon instruction is set      
            for point_id in self.point_items:
                self.point_items[point_id].point.hide()
                self.point_items[point_id].coords.hide()
            
            if self.polygon_item is not None:
                self.polygon_item.removeLastPoint()
                self.polygon_item.addPoint(event.scenePos())
                self.polygon_item.addPoint(event.scenePos())
                
                if self.is_ground_plane:    
                    pos_image = self.convertToNumpy(event.scenePos())
                    reproj_point = self.viewer.getReReprojectedPoints(pos_image)
                    pos_image_pyqt = self.convertToPyQt(reproj_point[0])
                    self.viewer.imagePlane.scene.polygon_item.removeLastPoint()
                    self.viewer.imagePlane.scene.polygon_item.addPoint(pos_image_pyqt)
                    self.viewer.imagePlane.scene.polygon_item.addPoint(pos_image_pyqt)
                    
                else:
                    pos_ground = self.convertToNumpy(event.scenePos())
                    reproj_point = self.viewer.getReprojectedPoints(pos_ground)
                    pos_ground_pyqt = self.convertToPyQt(reproj_point[0])
                    self.viewer.groundPlane.scene.polygon_item.removeLastPoint()
                    self.viewer.groundPlane.scene.polygon_item.addPoint(pos_ground_pyqt)
                    self.viewer.groundPlane.scene.polygon_item.addPoint(pos_ground_pyqt)

        return super(HomographyScene, self).mousePressEvent(event)

    def returnPoints(self):
        
        coords = list()
        for point_id in self.point_items:
            
            pts = self.point_items[point_id].points
            coords.append(pts)
        
        return np.array(coords)
    
    def convertToNumpy(self, point):

        return np.array((point.x(), point.y())).reshape(1, -1)

    def convertToPyQt(self, point):    
        
        return QtCore.QPointF(point[0], point[1])
        
    def returnUTMPoints(self):
        if not self.is_ground_plane:
            raise RuntimeWarning('This is not a ground plane. Cant export the UTM coords')
            
        coords_3d = list()
        for point_id in self.point_items:
            pts = self.point_items[point_id].utm_points
            coords_3d.append(pts)
        return np.array(coords_3d)
    
    def mouseMoveEvent(self, event):
        
        set_x, set_y = int(event.scenePos().x()), int(event.scenePos().y())
        if (set_x >= 0 and set_x <= self.width()) and (set_y >= 0 and set_y <= self.height() and self.current_mouse_coords is not None):
            if self.utm:
                x, y = int(event.scenePos().x()), int(event.scenePos().y())
                utm_x, utm_y = pixel_to_utm((x, y), self.transform_matrix)
                utm_x -= self.transform_matrix.c
                utm_y -= self.transform_matrix.f
                set_x, set_y = utm_x, utm_y
            
            self.current_mouse_coords.setPlainText(f'{set_x: .1f}, {set_y: .1f}')
            self.current_mouse_coords.setPos(int(event.scenePos().x()), int(event.scenePos().y()))
        
        # You can't draw the polygon unless the homography is set
        if self.current_instruction == Instructions.Polygon_Instruction and self.viewer.homMatrix is not None:

            self.polygon_item.movePoint(self.polygon_item.numPoints() - 1, event.scenePos())
            
            if self.is_ground_plane:
                pos_image = self.convertToNumpy(event.scenePos())
                reproj_point = self.viewer.getReReprojectedPoints(pos_image)
                pos_image_pyqt = self.convertToPyQt(reproj_point[0])
                self.viewer.imagePlane.scene.polygon_item.movePoint(self.viewer.imagePlane.scene.polygon_item.numPoints() - 1, pos_image_pyqt)
            else:
                pos_ground = self.convertToNumpy(event.scenePos())
                reproj_point = self.viewer.getReprojectedPoints(pos_ground)
                pos_ground_pyqt = self.convertToPyQt(reproj_point[0])
                self.viewer.groundPlane.scene.polygon_item.movePoint(self.viewer.groundPlane.scene.polygon_item.numPoints() - 1, pos_ground_pyqt)

        super(HomographyScene, self).mouseMoveEvent(event)
        
class HomographyViewer(QtWidgets.QGraphicsView):
    
    """
    A custom QGraphicsView widget for displaying and interacting with a homography scene.
    Signals:
        rightMouseButtonPressed: Signal emitted when the right mouse button is pressed.
            Parameters:
                - x (float): The x-coordinate of the scene position.
                - y (float): The y-coordinate of the scene position.
        rightMouseButtonReleased: Signal emitted when the right mouse button is released.
            Parameters:
                - x (float): The x-coordinate of the scene position.
                - y (float): The y-coordinate of the scene position.
        rightMouseButtonDoubleClicked: Signal emitted when the right mouse button is double-clicked.
            Parameters:
                - x (float): The x-coordinate of the scene position.
                - y (float): The y-coordinate of the scene position.
    Args:
        parent (QWidget): The parent widget.
        is_ground_plane (bool): Flag indicating whether the scene represents a ground plane.
        show_utm (bool): Flag indicating whether to show UTM coordinates.
    Attributes:
        zoomStack (list): A list to store the zoom stack.
        aspectRatioMode (Qt.AspectRatioMode): The aspect ratio mode for fitting the view.
        scene (HomographyScene): The homography scene.
        is_ground_plane (bool): Flag indicating whether the scene represents a ground plane.
    Methods:
        updateViewer(): Updates the viewer based on the zoom stack.
        mousePressEvent(event): Event handler for mouse press events.
        mouseReleaseEvent(event): Event handler for mouse release events.
        resizeEvent(event): Event handler for resize events.
        mouseDoubleClickEvent(event): Event handler for mouse double-click events.
    """

    rightMouseButtonPressed = pyqtSignal(float, float)
    rightMouseButtonReleased = pyqtSignal(float, float)
    rightMouseButtonDoubleClicked = pyqtSignal(float, float)

    def __init__(self, parent=None, is_ground_plane=False, show_utm=False):
        super(HomographyViewer, self).__init__(parent)
        
        self.setRenderHints(QtGui.QPainter.RenderHint.Antialiasing | QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        self.setMouseTracking(True)    
        self.zoomStack = list()    
        self.aspectRatioMode = Qt.AspectRatioMode.KeepAspectRatio
        self.scene = HomographyScene(parent, is_ground_plane=is_ground_plane, show_utm=show_utm)
        self.setScene(self.scene)
        self.is_ground_plane = is_ground_plane
        
        self.fitInView(self.scene.image_item, Qt.AspectRatioMode.KeepAspectRatio)
   
    def updateViewer(self):
    
        if len(self.zoomStack) and self.sceneRect().contains(self.zoomStack[-1]):
            self.fitInView(self.zoomStack[-1], Qt.AspectRatioMode.IgnoreAspectRatio)
        else:
            self.zoomStack = []
            self.fitInView(self.sceneRect(), self.aspectRatioMode)
   
    def mousePressEvent(self, event):
        
        if event.button() == Qt.MouseButton.RightButton:
            scenePos = self.mapToScene(event.pos())
            self.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
            self.rightMouseButtonPressed.emit(scenePos.x(), scenePos.y())
        
        super(HomographyViewer, self).mousePressEvent(event)
        
    def mouseReleaseEvent(self, event):
        
        if event.button() == Qt.MouseButton.RightButton:
            scenePos = self.mapToScene(event.pos())
            viewBBox = self.zoomStack[-1] if len(self.zoomStack) else self.sceneRect()
            selectionBBox = self.scene.selectionArea().boundingRect().intersected(viewBBox)
            self.scene.setSelectionArea(QtGui.QPainterPath())
            if selectionBBox.isValid() and (selectionBBox != viewBBox):
                self.zoomStack.append(selectionBBox)
                self.updateViewer()
            self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
            self.rightMouseButtonReleased.emit(scenePos.x(), scenePos.y())
        super(HomographyViewer, self).mouseReleaseEvent(event)
    
    def resizeEvent(self, event):
        self.updateViewer()
        
    def mouseDoubleClickEvent(self, event):
        
        scenePos = self.mapToScene(event.pos())
        if event.button() == Qt.MouseButton.RightButton:
            self.zoomStack = []
            self.updateViewer()
            self.rightMouseButtonDoubleClicked.emit(scenePos.x(), scenePos.y())
        
        QtWidgets.QGraphicsView.mouseDoubleClickEvent(self, event)

class AnnotationWindow(QtWidgets.QMainWindow):
    """
    A class representing the Annotation Window for the Homography Estimation Tool.
    Attributes:
        imagePlane (HomographyViewer): The viewer for the image plane.
        groundPlane (HomographyViewer): The viewer for the ground plane.
        homdialog (ImagePopup): The popup window for displaying the homography.
        homMatrix (numpy.ndarray): The homography matrix.
        filename (str): The path of the file being processed.
        fowrwad_milliseconds (int): The number of milliseconds to forward the video.
    Methods:
        __init__(self, parent=None): Initializes the AnnotationWindow object.
        actionDeleteLastPoint(self, view): Deletes the last point in the specified view.
        actionDeleteLastPolygon(self, view): Deletes the last polygon in the specified view.
        actionCalibrateCamera(self): Calibrates the camera using the image and ground points.
        actionLoadHomography(self): Loads the homography matrix from a file.
        actionLoadCameraParams(self): Loads the camera parameters from a file.
        setPoints(self, filename): Sets the image and ground points from the specified file.
    """
    def __init__(self, parent=None):
        super(AnnotationWindow, self).__init__(parent)


        self.setWindowTitle('Homography Estimation Tool')
        
        self.imagePlane = HomographyViewer(self)
        self.groundPlane = HomographyViewer(self, is_ground_plane=True, show_utm=True)

        self.imageLayout = QVBoxLayout()
        self.imageLayout.setContentsMargins(0, 0, 0, 0)
        self.imageLayout.addWidget(self.imagePlane)
        self.imageLayout.addWidget(self.groundPlane)
        self.homdialog = ImagePopup(self)
        self.homMatrix = None
        self.filename = None
        self.fowrwad_milliseconds = 1000
        
        QtGui.QShortcut(QtCore.Qt.Key.Key_Space, self, activated=self.actionPlayVideo)
        QtGui.QShortcut(QtCore.Qt.Key.Key_Right, self, activated=self.actionForwardVideo)
        QtGui.QShortcut(QtCore.Qt.Key.Key_Left, self, activated=self.actionBackwardVideo)
 
        # Create Menus
        self.create_menus()

        self.mainLayout = QVBoxLayout()
        self.deleteLastPointButtonImage = QPushButton()
        self.deleteLastPointButtonImage.setText('Delete Last Point - Image Plane')
        self.deleteLastPointButtonImage.clicked.connect(partial(self.actionDeleteLastPoint, self.imagePlane))
         
        self.deleteLastPointButtonGround = QPushButton()
        self.deleteLastPointButtonGround.setText('Delete Last Point - Ground Plane')
        self.deleteLastPointButtonGround.clicked.connect(partial(self.actionDeleteLastPoint, self.groundPlane))
        self.deleteLastPolygonButton = QPushButton()
        self.deleteLastPolygonButton.setText('Delete Last Polygon') 
        self.deleteLastPolygonButton.clicked.connect(partial(self.actionDeleteLastPolygon, self.groundPlane))
        
        self.savePointsButton = QPushButton() 
        self.savePointsButton.setText('Save Progress')
        self.savePointsButton.clicked.connect(self.actionSaveProgress)
        
        self.savePolygonsButton = QPushButton()
        self.savePolygonsButton.setText('Save Polygons')
        self.savePolygonsButton.clicked.connect(self.actionSavePolygons)

        self.homographyButton = QPushButton()
        self.homographyButton.setText('Homography')
        self.homographyButton.clicked.connect(self.actionHomography)
        
        self.calibrationButton = QPushButton()
        self.calibrationButton.setText('Calibrate Camera')
        self.calibrationButton.clicked.connect(self.actionCalibrateCamera)
        
        self.reprojErrorButton = QPushButton()
        self.reprojErrorButton.setText('Calculate Reprojection Error')
        self.reprojErrorButton.clicked.connect(self.actionReprojError)
        
        self.loadPointsButton = QPushButton()
        self.loadPointsButton.setText('Load Points')
        self.loadPointsButton.clicked.connect(self.actionLoadPoints)
        
        self.loadHomographyButton = QPushButton()
        self.loadHomographyButton.setText('Load Homography')
        self.loadHomographyButton.clicked.connect(self.actionLoadHomography)
        
        self.loadCameraParams = QPushButton()
        self.loadCameraParams.setText('Load Camera Intrinsics')
        self.loadCameraParams.clicked.connect(self.actionLoadCameraParams)
        
        self.loadROI = QPushButton()
        self.loadROI.setText('Load ROI')
        self.loadROI.clicked.connect(self.actionLoadROI)
        
        self.reprojErroLabel = QtWidgets.QLabel()
        self.reprojErroLabel.setText('')
        self.reprojErroLabelText = QtWidgets.QLabel()
        self.reprojErroLabelText.setText('Homography error: ')
        

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.setContentsMargins(0, 0, 0, 0)
        self.buttonLayout.addWidget(self.deleteLastPointButtonImage)
        self.buttonLayout.addWidget(self.deleteLastPointButtonGround)
        self.buttonLayout.addWidget(self.deleteLastPolygonButton)
        self.buttonLayout.addWidget(self.homographyButton)
        self.buttonLayout.addWidget(self.loadHomographyButton)
        self.buttonLayout.addWidget(self.savePointsButton)
        self.buttonLayout.addWidget(self.savePolygonsButton)
        self.buttonLayout.addWidget(self.reprojErrorButton)
        self.buttonLayout.addWidget(self.loadPointsButton)
        self.buttonLayout.addWidget(self.loadROI)
        self.buttonLayout.addWidget(self.loadCameraParams)
        self.buttonLayout.addWidget(self.calibrationButton)
        
        self.buttonLayout.addWidget(self.reprojErroLabelText)
        self.buttonLayout.addWidget(self.reprojErroLabel)
        
        self.mainLayout = QVBoxLayout()
        self.mainLayout.addLayout(self.imageLayout)
        self.mainLayout.addLayout(self.buttonLayout)
        
        QtGui.QShortcut(QtCore.Qt.Key.Key_I, self, activated=partial(self.imagePlane.scene.setCurrentInstruction, Instructions.Point_Instruction))
        QtGui.QShortcut(QtCore.Qt.Key.Key_G, self, activated=partial(self.groundPlane.scene.setCurrentInstruction, Instructions.Point_Instruction))
        
        # Make the pairs for the Ground Plane to draw the polygons
        QtGui.QShortcut(QtCore.Qt.Key.Key_P, self, activated=partial(self.groundPlane.scene.setCurrentInstruction, Instructions.Polygon_Instruction))
        QtGui.QShortcut(QtCore.Qt.Key.Key_Escape, self, activated=partial(self.groundPlane.scene.setCurrentInstruction, Instructions.No_Instruction))
        
        QtGui.QShortcut(QtCore.Qt.Key.Key_C, self, activated=self.actionResetAll)
        QtGui.QShortcut(QtCore.Qt.Key.Key_S, self, activated=self.actionSaveProgress)
        
        wid = QWidget()
        self.setCentralWidget(wid)
        wid.setLayout(self.mainLayout)
        
    def actionDeleteLastPoint(self, view):
        
        view.scene.deleteLastPoint()
    
    def actionDeleteLastPolygon(self, view):
        view.scene.deleteLastPolygon()
    
    def actionCalibrateCamera(self): # Only supports pinhole camera calibration
        try:
            if len(self.imagePlane.scene.point_items.keys()) and len(self.groundPlane.scene.point_items.keys()) and self.groundPlane.scene.utm:
                image_points = self.imagePlane.scene.returnPoints()
                if self.groundPlane.scene.utm:
                    georef_points = self.groundPlane.scene.returnUTMPoints()
                
                imagePoints_mat = matlab.double(image_points.tolist())
                worldPoints_mat = matlab.double(georef_points.tolist())
                cameraIntrinsics = eng.eval("cameraParams.Intrinsics", nargout=1)
                eng.workspace["worldPoints_mat"] = worldPoints_mat
                eng.workspace["worldPose"] = eng.estworldpose(
                    imagePoints_mat,
                    worldPoints_mat,
                    cameraIntrinsics,
                    "MaxNumTrials",
                    matlab.single(2000),
                    "Confidence",
                    matlab.single(98),
                    "MaxReprojectionError",
                    matlab.single(2),
                    nargout=1
                )
                eng.eval(f"""
                        pcshow(worldPoints_mat, VerticalAxis="Y", VerticalAxisDir="down", MarkerSize=30);
                        hold on
                        plotCamera(Size=10, Orientation=worldPose.R', Location=worldPose. Translation);
                        hold off
                        """, nargout=0)
                K, R, t = np.array(eng.eval("cameraParams.Intrinsics.K")), np.array(eng.eval("worldPose.R")), np.array(eng.eval("worldPose.Translation")).reshape((3, 1))
                
                name = os.path.splitext(os.path.basename(self.filename))[0]
                if not os.path.exists(name):
                    os.makedirs(name)
                
                np.savetxt(os.path.join(name, 'K.txt'), K, fmt='%.10f')
                np.savetxt(os.path.join(name, 'R.txt'), R, fmt='%.10f')
                np.savetxt(os.path.join(name, 't.txt'), t, fmt='%.10f')
        except:
            print('Error in calibrating the camera..Either matlab engine is not installed or the points are not set properly')
    

    def actionLoadHomography(self):
            
        if self.imagePlane.scene.file_loaded and self.groundPlane.scene.file_loaded:
            fileName, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Homography File",
                    QtCore.QDir.homePath())
            if fileName:
                self.homMatrix = np.loadtxt(fileName).astype(float)
        else:
            diag = QMessageBox()
            diag.setWindowTitle('Runtime Warning..')
            diag.setText('Please load the ground and camera views first. Then try to load the homography!')
            diag.exec()
    
    def actionLoadCameraParams(self):
        
        if self.groundPlane.scene.file_loaded and self.groundPlane.scene.utm:
            fileName, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Camera Parameters File",
                    QtCore.QDir.homePath())
            if fileName:
                eng.eval(f"load('{fileName}')", nargout=0)
            
        else:
            diag = QMessageBox()
            diag.setWindowTitle('Runtime Warning..')
            diag.setText('You are loading camera parameters without using GeoReF points. Use the Orthophotos for calibrating the extrinsics.')
            diag.exec()
            
    def setPoints(self, filename):
        
        image_points = np.loadtxt(filename)
        ground_points = np.loadtxt(filename.replace('image_points', 'ground_points'))
        
        # Set image points
        self.imagePlane.scene.load_points(image_points)
        
        # Set ground points
        self.groundPlane.scene.load_points(ground_points)
        
        # Set the georef points
        if self.groundPlane.scene.utm:
            georef_points = np.loadtxt(filename.replace('image_points', 'georef_points'))
            self.groundPlane.scene.load_utm_points(georef_points)

    def actionLoadPoints(self):
        
        if self.imagePlane.scene.file_loaded and self.groundPlane.scene.file_loaded:
            
            fileName, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open SetPoints File", 
                    QtCore.QDir.homePath())
            if fileName:
                self.setPoints(fileName)
        else:
            diag = QMessageBox()
            diag.setWindowTitle('Runtime Warning..')
            diag.setText('Please load the ground and camera views first. Then try to load the set points!')
            diag.exec()

    def actionSavePolygons(self):
        
        for label, polygon in self.imagePlane.scene.polygon_items.items():
            polypoints = polygon.polypoints
            polypoints[:, 0] /= self.imagePlane.scene.image_width
            polypoints[:, 1] /= self.imagePlane.scene.image_height
            self.imagePlane.scene.roi[str(label + 1)]['roi'] = polypoints.tolist()
        
        with open(f"{os.path.splitext(os.path.basename(self.filename))[0]}.json", 'w') as f:
            json.dump(self.imagePlane.scene.roi, f)
            
    def actionSaveProgress(self):
    
        if len(self.imagePlane.scene.point_items.keys()) and len(self.groundPlane.scene.point_items.keys()):
            image_points = self.imagePlane.scene.returnPoints()
            ground_points = self.groundPlane.scene.returnPoints()
            georef_points = None
            if self.groundPlane.scene.utm:
                georef_points = self.groundPlane.scene.returnUTMPoints()

            name = os.path.splitext(os.path.basename(self.filename))[0]
            if not os.path.exists(name):
                os.makedirs(name)
            
            np.savetxt(os.path.join(name, 'image_points.txt'), image_points, fmt='%d')
            np.savetxt(os.path.join(name, 'ground_points.txt'), ground_points, fmt='%d')
            if self.homMatrix is not None:
                np.savetxt(os.path.join(name, 'homography.txt'), self.homMatrix, fmt='%.5f')
            if georef_points is not None:
                 np.savetxt(os.path.join(name, 'georef_points.txt'), georef_points, fmt='%d')

    def actionResetAll(self):
        
        # First save the progress and delete everything
        self.actionSaveProgress()
        
        while self.imagePlane.scene.point_id > 0:
            self.imagePlane.scene.deleteLastPoint()
        
        while self.groundPlane.scene.point_id > 0:
            self.groundPlane.scene.deleteLastPoint()
        
        while self.groundPlane.scene.polygon_id > 0:
            self.groundPlane.scene.deleteLastPolygon()
        
        while self.imagePlane.scene.polygon_id > 0:
            self.imagePlane.scene.deleteLastPolygon()
        
        self.imagePlane.scene.clear()
        self.imagePlane.scene.set_default()
        self.groundPlane.scene.clear()
        self.groundPlane.scene.set_default()
    
        self.homMatrix = None
        self.reprojErroLabel.setText('')
        self.filename = None
        self.homdialog.resetImage()
        
    def actionLoadROI(self):
            
            if self.imagePlane.scene.file_loaded and self.groundPlane.scene.file_loaded:
                fileName, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open ROI File",
                        QtCore.QDir.homePath())
                if fileName is not None and self.homMatrix is not None:
                    self.imagePlane.scene.load_roi(fileName)
            else:
                diag = QMessageBox()
                diag.setWindowTitle('Runtime Warning..')
                diag.setText('Please load the ground and camera views first. Then try to load the set points!')
                diag.exec()
    
    
    def actionReprojError(self):
        
        if self.homMatrix is not None:
            image_points = self.imagePlane.scene.returnPoints()
            ground_points = self.groundPlane.scene.returnPoints()
            timage_points = self.getReprojectedPoints(image_points)
            
            errors = np.linalg.norm(timage_points - ground_points, axis=1)
            rmse = np.sqrt(np.mean(errors ** 2))
            self.reprojErroLabel.setText('%.2f' % rmse)
        else:
            self.reprojErroLabel.setText('ERROR!')

    def getHomographyMatrix(self, image_points, ground_points):
        
        cv2hom = cv2.findHomography(image_points, ground_points)[0]
        self.homMatrix = cv2hom
    
    def getReprojectedPoints(self, image_points):
        
        himage_points = np.hstack((image_points, np.ones((image_points.shape[0], 1))))
        timage_points = himage_points @ self.homMatrix.T    
        timage_points = timage_points[:, :2] / timage_points[:, [2]]
        return timage_points
    
    def getReReprojectedPoints(self, ground_points):
        
        hground_points = np.hstack((ground_points, np.ones((ground_points.shape[0], 1))))
        tground_points = hground_points @ np.linalg.inv(self.homMatrix).T    
        tground_points = tground_points[:, :2] / tground_points[:, [2]]
        return tground_points
    
    def actionHomography(self):
        
        image_points = self.imagePlane.scene.returnPoints()
        ground_points = self.groundPlane.scene.returnPoints()
        
        if (image_points.shape[0] >= 4 and ground_points.shape[0] >= 4) and (image_points.shape[0] == ground_points.shape[0]):
            self.getHomographyMatrix(image_points, ground_points)
            
            if self.imagePlane.scene.file_loaded == 'image':
                cv_image = cv2.imread(self.imagePlane.scene.image_filename)
            else:
                vread = cv2.VideoCapture(self.imagePlane.scene.image_filename)
                _, cv_image = vread.read()
                vread.release()
            if 'tif' in self.groundPlane.scene.image_filename: 
                orthophoto = rasterio.open(self.groundPlane.scene.image_filename)
                red, green, blue = orthophoto.read(1), orthophoto.read(2), orthophoto.read(3)
                cv_ground = np.dstack((blue, green, red))
                
            reprojected_points = self.getReprojectedPoints(image_points)
            warped_image = cv2.warpPerspective(cv_image, self.homMatrix, (cv_ground.shape[1], cv_ground.shape[0]))
            alpha = 0.7
            beta = (1.0 - alpha)
            result = cv2.addWeighted(warped_image, alpha, cv_ground, beta, 0.0)
            self.homdialog.setImage(result)
            for p, rp in zip(ground_points.astype(int), reprojected_points.astype(int)):
                cv_ground = cv2.circle(cv_ground, p, 2, (0, 255, 0), 2)
                cv_ground = cv2.circle(cv_ground, rp, 2, (0, 0, 255), 2)
            
            self.homdialog.setImage(cv_ground, reproject=True)
            self.homdialog.show()
    
    def create_menus(self):
        
        menu_file = self.menuBar().addMenu("File")
        load_image_action = menu_file.addAction("&Load Image Plane Image")
        load_ground_action = menu_file.addAction("&Load Ground Plane Image")
        
        load_image_action.triggered.connect(partial(self.load_image, self.imagePlane))
        load_ground_action.triggered.connect(partial(self.load_image, self.groundPlane))
        
        menu_instructions = self.menuBar().addMenu("Intructions")
        polygon_action1 = menu_instructions.addAction("Point - Image Plane")
        polygon_action2 = menu_instructions.addAction("Point - Ground Plane")
        polygon_action3 = menu_instructions.addAction("Polygon - Ground Plane")
        
        polygon_action1.triggered.connect(partial(self.imagePlane.scene.setCurrentInstruction, Instructions.Point_Instruction))
        polygon_action2.triggered.connect(partial(self.groundPlane.scene.setCurrentInstruction, Instructions.Point_Instruction))
        polygon_action3.triggered.connect(partial(self.groundPlane.scene.setCurrentInstruction, Instructions.Polygon_Instruction))
    
    @QtCore.pyqtSlot()
    def load_image(self, view):
        
        formats = '*.png *.jpg *.bmp *.tif'
        if view == self.imagePlane:
            formats += ' *.mp4'
            
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(self, 
            "Open Image",
            QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.PicturesLocation), #QtCore.QDir.currentPath(), 
            f"Image Files ({formats})")
        
        if filename:
            view.scene.load_image(filename)
            if view.scene.item_loaded == 'image':
                view.fitInView(view.scene.image_item, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
                view.centerOn(view.scene.image_item)
            else:
                view.fitInView(view.scene.video_item, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
                view.centerOn(view.scene.video_item)
            
        if view ==  self.imagePlane:
            self.filename = filename   
    
    def actionPlayVideo(self):
        
        if self.imagePlane.scene.item_loaded == 'video':
            if self.imagePlane.scene.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.imagePlane.scene.player.pause()
            else:
                self.imagePlane.scene.player.play() 
    
    def actionForwardVideo(self):
        
        if self.imagePlane.scene.item_loaded == 'video':
            curr_position = self.imagePlane.scene.player.position()
            next_position = min(curr_position + self.fowrwad_milliseconds, self.imagePlane.scene.player.duration())
            self.imagePlane.scene.player.setPosition(next_position)
        
    def actionBackwardVideo(self):
        
        if self.imagePlane.scene.item_loaded == 'video':
            curr_position = self.imagePlane.scene.player.position()
            next_position = max(0, curr_position - self.fowrwad_milliseconds)
            self.imagePlane.scene.player.setPosition(next_position)
                
if __name__ == '__main__':
    import sys

    app = QtWidgets.QApplication(sys.argv)
    w = AnnotationWindow()
   
    w.showMaximized()
    sys.exit(app.exec())