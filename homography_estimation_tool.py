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
import rasterio

# Import the Matlab engine if installed
try:
    import matlab.engine
    eng = matlab.engine.start_matlab()
except ImportError:
    print('Matlab engine is not installed in the environment..skipping.')


def convert_cv_qt(cv_img, rgb=False):
    
    rgb_image = cv_img
    if not rgb:
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        
    h, w, ch = rgb_image.shape
    bytes_per_line = ch * w
    convert_to_Qt_format = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
    p = convert_to_Qt_format.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio)
    return QtGui.QPixmap.fromImage(p)

def pixel_to_utm(px, transform_matrix):
    utm_x, utm_y = rasterio.transform.xy(transform_matrix, px[1], px[0])
    return utm_x, utm_y

class Instructions(Enum):
    No_Instruction = 0
    Point_Instruction = 1

class ImagePopup(QtWidgets.QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        
        self.setWindowTitle('Homography Image')
        self.label_warped = QtWidgets.QLabel(self)
        self.label_reprojected = QtWidgets.QLabel(self)
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.label_warped)
        self.layout.addWidget(self.label_reprojected)
        self.setLayout(self.layout)
        self.adjustSize()
    
    def setImage(self, img, reproject=False):
        
        pix_img = convert_cv_qt(img)
        if reproject:
            self.label_reprojected.setPixmap(pix_img)
        else:
            self.label_warped.setPixmap(pix_img)
        
class GripItem(QtWidgets.QGraphicsPathItem):
    
    circle = QtGui.QPainterPath()
    circle.addEllipse(QtCore.QRectF(-10, -10, 20, 20))
    square = QtGui.QPainterPath()
    square.addRect(QtCore.QRectF(-15, -15, 30, 30))
    
    def __init__(self, annotation_item, id=0):
        super(GripItem, self).__init__()
        
        self.annotation_item = annotation_item
        self.id = id
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
            self.annotation_item.movePoint(value, self.id)
        return super(GripItem, self).itemChange(change, value)

class PointAnnotation(QtWidgets.QGraphicsItem):
    
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

    def movePoint(self, pos, id):
            
        self.c = self.mapFromScene(pos)
        self.point.setPos(self.c)
        self.coords.setPos(self.c)
        self.coords.setPlainText(f'ID: {id}')

class HomographyScene(QtWidgets.QGraphicsScene):
    
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
        self.instruction = Instructions.No_Instruction
        self.current_mouse_coords = None
       
        self.point_items = defaultdict()
        self.point_id = 0
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
        
    def setCurrentInstruction(self, instruction):
        
        if instruction == Instructions.No_Instruction and self.point_item is not None:
            self.point_items[self.point_id - 1] = self.point_item
            self.point_item = None

        self.current_instruction = instruction
        if instruction == Instructions.Point_Instruction and self.point_item is None:
            self.point_item = PointAnnotation()
            self.addItem(self.point_item)
            self.point_id += 1
    
    def deleteLastPoint(self):
        
        if len(self.point_items.keys()) > 0:
            self.point_id -= 1
            self.removeItem(self.point_items[self.point_id].point)
            self.removeItem(self.point_items[self.point_id])
            del self.point_items[self.point_id]
            
    def mousePressEvent(self, event):
        
        if self.current_instruction == Instructions.Point_Instruction:
            if self.point_item.point is None:
                
                self.point_item.setPoint(event.scenePos(), self.point_id - 1)
                self.point_item.set = True
                if self.utm:
                    x, y = tuple(map(int, self.point_item.points))
                    utm_x, utm_y = pixel_to_utm((x, y), self.transform_matrix)
                    elevation = self.elevation_map[y, x]
                    self.point_item.utm_coords = [utm_x, utm_y, elevation]
                self.setCurrentInstruction(Instructions.No_Instruction)
        
        return super(HomographyScene, self).mousePressEvent(event)

    def returnPoints(self):
        
        coords = list()
        for point_id in self.point_items:
            
            pts = self.point_items[point_id].points
            coords.append(pts)
        
        return np.array(coords)
    
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
                set_x, set_y = utm_x, utm_y
            
            self.current_mouse_coords.setPlainText(f'{set_x: .1f}, {set_y: .1f}')
            self.current_mouse_coords.setPos(int(event.scenePos().x()), int(event.scenePos().y()))

        super(HomographyScene, self).mouseMoveEvent(event)
        
class HomographyViewer(QtWidgets.QGraphicsView):

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
    def __init__(self, parent=None):
        super(AnnotationWindow, self).__init__(parent)

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
        
        self.savePointsButton = QPushButton()
        self.savePointsButton.setText('Save Progress')
        self.savePointsButton.clicked.connect(self.actionSaveProgress)

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
        
        self.loadCameraParams = QPushButton()
        self.loadCameraParams.setText('Load Camera Intrinsics')
        self.loadCameraParams.clicked.connect(self.actionLoadCameraParams)
        
        self.reprojErroLabel = QtWidgets.QLabel()
        self.reprojErroLabel.setText('')
        self.reprojErroLabelText = QtWidgets.QLabel()
        self.reprojErroLabelText.setText('Homography error: ')
        

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.setContentsMargins(0, 0, 0, 0)
        self.buttonLayout.addWidget(self.deleteLastPointButtonImage)
        self.buttonLayout.addWidget(self.deleteLastPointButtonGround)
        self.buttonLayout.addWidget(self.homographyButton)
        self.buttonLayout.addWidget(self.savePointsButton)
        self.buttonLayout.addWidget(self.reprojErrorButton)
        self.buttonLayout.addWidget(self.loadPointsButton)
        self.buttonLayout.addWidget(self.loadCameraParams)
        self.buttonLayout.addWidget(self.calibrationButton)
        
        self.buttonLayout.addWidget(self.reprojErroLabelText)
        self.buttonLayout.addWidget(self.reprojErroLabel)
        
        
        self.mainLayout = QVBoxLayout()
        self.mainLayout.addLayout(self.imageLayout)
        self.mainLayout.addLayout(self.buttonLayout)
        
        QtGui.QShortcut(QtCore.Qt.Key.Key_I, self, activated=partial(self.imagePlane.scene.setCurrentInstruction, Instructions.Point_Instruction))
        QtGui.QShortcut(QtCore.Qt.Key.Key_G, self, activated=partial(self.groundPlane.scene.setCurrentInstruction, Instructions.Point_Instruction))
        QtGui.QShortcut(QtCore.Qt.Key.Key_C, self, activated=self.actionResetAll)
        QtGui.QShortcut(QtCore.Qt.Key.Key_S, self, activated=self.actionSaveProgress)
        
        wid = QWidget()
        self.setCentralWidget(wid)
        wid.setLayout(self.mainLayout)
        
    def actionDeleteLastPoint(self, view):
        
        view.scene.deleteLastPoint()
    
    def actionCalibrateCamera(self):
        
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
                     plotCamera(Size=10, Orientation=worldPose.R', Location=worldPose.Translation);
                     hold off
                     """, nargout=0)
            K, R, t = np.array(eng.eval("cameraParams.Intrinsics.K")), np.array(eng.eval("worldPose.R")), np.array(eng.eval("worldPose.Translation")).reshape((3, 1))
            
            name = os.path.splitext(os.path.basename(self.filename))[0]
            if not os.path.exists(name):
                os.makedirs(name)
            
            np.savetxt(os.path.join(name, name + '_K.txt'), K, fmt='%.10f')
            np.savetxt(os.path.join(name, name + '_R.txt'), R, fmt='%.10f')
            np.savetxt(os.path.join(name, name + '_t.txt'), t, fmt='%.10f')
            
    def actionLoadCameraParams(self):
        
        if self.groundPlane.scene.file_loaded and self.groundPlane.scene.utm:
            fileName, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Camera Parameters File",
                    QtCore.QDir.homePath())
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
            
            self.setPoints(fileName)
        else:
            diag = QMessageBox()
            diag.setWindowTitle('Runtime Warning..')
            diag.setText('Please load the ground and camera views first. Then try to load the set points!')
            diag.exec()

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
            
            np.savetxt(os.path.join(name, name + '_image_points.txt'), image_points, fmt='%d')
            np.savetxt(os.path.join(name, name + '_ground_points.txt'), ground_points, fmt='%d')
            if self.homMatrix is not None:
                np.savetxt(os.path.join(name, name + '_homography.txt'), self.homMatrix, fmt='%.5f')
            if georef_points is not None:
                 np.savetxt(os.path.join(name, name + '_georef_points.txt'), georef_points, fmt='%d')

    def actionResetAll(self):
        
        # First save the progress and delete everything
        self.actionSaveProgress()
        
        while self.imagePlane.scene.point_id > 0:
            self.imagePlane.scene.deleteLastPoint()
        
        while self.groundPlane.scene.point_id > 0:
            self.groundPlane.scene.deleteLastPoint()
        
        self.imagePlane.scene.clear()
        self.imagePlane.scene.set_default()
        self.groundPlane.scene.clear()
        self.groundPlane.scene.set_default()
    
        self.homMatrix = None
        self.reprojErroLabel.setText('')
        self.filename = None
    
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
        
        polygon_action1.triggered.connect(partial(self.imagePlane.scene.setCurrentInstruction, Instructions.Point_Instruction))
        polygon_action2.triggered.connect(partial(self.groundPlane.scene.setCurrentInstruction, Instructions.Point_Instruction))
    
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