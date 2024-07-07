from enum import Enum
from functools import partial
from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (QHBoxLayout, QPushButton, QVBoxLayout, QWidget)
import cv2
import numpy as np
from collections import defaultdict
import os

def convert_cv_qt(cv_img):
    rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb_image.shape
    bytes_per_line = ch * w
    convert_to_Qt_format = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
    p = convert_to_Qt_format.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio)
    return QtGui.QPixmap.fromImage(p)

class Instructions(Enum):
    No_Instruction = 0
    Point_Instruction = 1

class ImagePopup(QtWidgets.QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        
        self.setWindowTitle('Homography Image')
        self.label = QtWidgets.QLabel(self)
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.label)
        self.setLayout(self.layout)
        self.adjustSize()
    
    def setImage(self, img):
        pix_img = convert_cv_qt(img)
        self.label.setPixmap(pix_img)
        
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
        
    @property
    def points(self):
        return (self.point.x(), self.point.y())

    def setPoint(self, p, id):
        
        self.c = self.mapFromScene(p)
        self.point = GripItem(self, id)
        self.scene().addItem(self.point)
        self.point.setPos(self.c)
        self.coords.setPlainText(f'ID: {id} {self.c.x(): .2f}, {self.c.y(): .2f}')
        self.coords.setPos(self.c)

    def movePoint(self, pos, id):
            
        self.c = self.mapFromScene(pos)
        self.point.setPos(self.c)
        self.coords.setPos(self.c)
        self.coords.setPlainText(f'ID: {id} {self.c.x(): .2f}, {self.c.y(): .2f}')

class HomographyScene(QtWidgets.QGraphicsScene):
    
    def __init__(self, parent=None):
        
        super(HomographyScene, self).__init__(parent)
        
        self.viewer = parent
        self.set_default()
    
    def set_default(self):
        self.image_item = QtWidgets.QGraphicsPixmapItem()
        self.image_item.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.CrossCursor))
        self.current_instruction = Instructions.No_Instruction
        self.addItem(self.image_item)
        self.point_item = None
        self.instruction = Instructions.No_Instruction
        self.current_mouse_coords = self.addText('', QtGui.QFont('Arial', 10, QtGui.QFont.Weight.Bold))
        self.current_mouse_coords.setDefaultTextColor(QtGui.QColor(255, 0, 0))
        self.current_mouse_coords.setPos(0, 0)
        self.point_items = defaultdict()
        self.point_id = 0
        self.image_width, self.image_height = None, None
    
    def load_image(self, filename):
        
        self.image_filename = filename
        self.image_item.setPixmap(QtGui.QPixmap(filename))
        self.setSceneRect(self.image_item.boundingRect())
        
        self.image_height, self.image_width = self.height(), self.width()
    
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
                self.setCurrentInstruction(Instructions.No_Instruction)
        
        return super(HomographyScene, self).mousePressEvent(event)

    def returnPoints(self):
        
        coords = list()
        for point_id in self.point_items:
            
            pts = self.point_items[point_id].points
            coords.append(pts)
        
        return np.array(coords)
    
    def mouseMoveEvent(self, event):
        
        self.current_mouse_coords.setPlainText(f'{event.scenePos().x(): .1f}, {event.scenePos().y(): .1f}')
        self.current_mouse_coords.setPos(event.scenePos().x(), event.scenePos().y())

        super(HomographyScene, self).mouseMoveEvent(event)
        
class HomographyViewer(QtWidgets.QGraphicsView):

    rightMouseButtonPressed = pyqtSignal(float, float)
    rightMouseButtonReleased = pyqtSignal(float, float)
    rightMouseButtonDoubleClicked = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super(HomographyViewer, self).__init__(parent)
        
        self.setRenderHints(QtGui.QPainter.RenderHint.Antialiasing | QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        self.setMouseTracking(True)    
        self.zoomStack = list()    
        self.aspectRatioMode = Qt.AspectRatioMode.KeepAspectRatio
        self.scene = HomographyScene(parent)
        self.setScene(self.scene)
        
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
        self.groundPlane = HomographyViewer(self)

        self.imageLayout = QVBoxLayout()
        self.imageLayout.setContentsMargins(0, 0, 0, 0)
        self.imageLayout.addWidget(self.imagePlane)
        self.imageLayout.addWidget(self.groundPlane)
        self.homdialog = ImagePopup(self)
        self.homMatrix = None
        self.filename = None
        
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
        
        self.reprojErrorButton = QPushButton()
        self.reprojErrorButton.setText('Calculate Reprojection Error')
        self.reprojErrorButton.clicked.connect(self.actionReprojError)
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
        
    def actionSaveProgress(self):
        
        image_points = self.imagePlane.scene.returnPoints()
        ground_points = self.groundPlane.scene.returnPoints()
        name = os.path.splitext(os.path.basename(self.filename))[0]
        np.savetxt(name + '_image_points.txt', image_points, fmt='%d', delimiter=' ')
        np.savetxt(name + '_ground_points.txt', ground_points, fmt='%d', delimiter=' ')
        if self.homMatrix is not None:
            np.savetxt(name + '_homography.txt', self.homMatrix, fmt='%.5f', delimeter=' ')
    
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
            himage_points = np.hstack((image_points, np.ones((image_points.shape[0], 1))))
            timage_points = himage_points @ self.homMatrix.T
            
            timage_points = timage_points[:, :2] / timage_points[:, [2]]
            print(timage_points, ground_points)
            errors = np.linalg.norm(timage_points - ground_points, axis=1)
            rmse = np.sqrt(np.mean(errors ** 2))
            self.reprojErroLabel.setText('%.2f' % rmse)
        else:
            self.reprojErroLabel.setText('ERROR!')

    def actionHomography(self):
        
        image_points = self.imagePlane.scene.returnPoints()
        ground_points = self.groundPlane.scene.returnPoints()
        sx = self.imagePlane.scene.image_width / self.groundPlane.scene.image_width 
        sy = self.imagePlane.scene.image_height / self.groundPlane.scene.image_height
        
        cv2hom = cv2.findHomography(image_points, ground_points)[0]
        self.homMatrix = cv2hom
        
        cv_image, cv_ground = cv2.imread(self.imagePlane.scene.image_filename), cv2.imread(self.groundPlane.scene.image_filename)
        warped_image = cv2.warpPerspective(cv_image, cv2hom, (cv_ground.shape[1], cv_ground.shape[0]))
        alpha = 0.7
        beta = (1.0 - alpha)
        result = cv2.addWeighted(warped_image, alpha, cv_ground, beta, 0.0)
        self.homdialog.setImage(result)
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
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(self, 
            "Open Image",
            QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.PicturesLocation), #QtCore.QDir.currentPath(), 
            "Image Files (*.png *.jpg *.bmp)")
        
        if filename:
            view.scene.load_image(filename)
            view.fitInView(view.scene.image_item, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
            view.centerOn(view.scene.image_item)
            
        if view ==  self.imagePlane:
            self.filename = filename    

if __name__ == '__main__':
    import sys

    app = QtWidgets.QApplication(sys.argv)
    w = AnnotationWindow()
   
    w.showMaximized()
    sys.exit(app.exec())