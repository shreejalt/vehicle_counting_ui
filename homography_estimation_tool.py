from enum import Enum
from functools import partial
from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (QHBoxLayout, QPushButton, QVBoxLayout, QWidget)
import json
from collections import defaultdict

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

class Instructions(Enum):
    No_Instruction = 0
    Point_Instruction = 1


class PointAnnotation(QtWidgets.QGraphicsItem):
    
    def __init__(self, parent=None):
        super(PointAnnotation, self).__init__(parent)
        self.setZValue(10)
        self.setAcceptHoverEvents(True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.coords = QtWidgets.QGraphicsTextItem('', self)
        self.coords.setDefaultTextColor(QtGui.QColor(0, 255, 0))
        self.coords.setPos(0, 0)
        self.coords.setFont(QtGui.QFont('Arial', 20, QtGui.QFont.Weight.Bold))
        self.point = None
        
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

        
class RectangleAnnotation(QtWidgets.QGraphicsRectItem):
    
    def __init__(self, parent=None):
        super(RectangleAnnotation, self).__init__(parent)
        
        self.setZValue(10)
        self.setPen(QtGui.QPen(QtGui.QColor('green'), 2))
        self.setAcceptHoverEvents(True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.label = -1
        self.top_left, self.bottom_right = None, None
        self.top_left_item, self.bottom_right_item = None, None
        
        self.top_left_coords = QtWidgets.QGraphicsTextItem('', self)
        self.top_left_coords.setDefaultTextColor(QtGui.QColor(0, 255, 0))
        self.top_left_coords.setPos(0, 0)
        self.top_left_coords.setFont(QtGui.QFont('Arial', 30, QtGui.QFont.Weight.Bold))
        
        self.bottom_right_coords = QtWidgets.QGraphicsTextItem('', self)
        self.bottom_right_coords.setDefaultTextColor(QtGui.QColor(0, 255, 0))
        self.bottom_right_coords.setPos(0, 0)
        self.bottom_right_coords.setFont(QtGui.QFont('Arial', 30, QtGui.QFont.Weight.Bold))
        
        self.size_text =  QtWidgets.QGraphicsTextItem('', self)
        self.size_text.setDefaultTextColor(QtGui.QColor(0, 0, 255))
        self.size_text.setPos(0, 0)
        self.size_text.setFont(QtGui.QFont('Arial', 30, QtGui.QFont.Weight.Bold))

    @property
    def points(self):
        return [self.top_left.x(), self.top_left.y(), self.bottom_right.x(), self.bottom_right.y()]
    
    def setTopLeft(self, p):
        self.top_left = self.mapFromScene(p)
        self.top_left_item = GripItem(self, annotation_name='top_left')
        self.scene().addItem(self.top_left_item)
        self.top_left_item.setPos(p)
        self.top_left_coords.setPlainText(f'{self.top_left.x(): .2f}, {self.top_left.y(): .2f}')
        self.top_left_coords.setPos(p)
    
    def setBottomRight(self, p):
        self.bottom_right = self.mapFromScene(p)
        self.bottom_right_item = GripItem(self, annotation_name='bottom_right')
        self.scene().addItem(self.bottom_right_item)
        self.bottom_right_item.setPos(p)
        self.bottom_right_coords.setPlainText(f'{self.bottom_right.x(): .2f}, {self.bottom_right.y(): .2f}')
        self.bottom_right_coords.setPos(p)

        tlx, tly, brx, bry = self.top_left.x(), self.top_left.y(), self.bottom_right.x(), self.bottom_right.y()
        self.size_text.setPlainText(f'{(brx - tlx): .2f} X {(bry - tly): .2f}')
        self.size_text.setPos((tlx + brx) // 2 - 50, (tly + bry) // 2)
    
    def movePoint(self, pos, name):
        
        if name == 'top_left' and self.top_left is not None:
            self.top_left = self.mapFromScene(pos)
            self.top_left_coords.setPlainText(f'{self.top_left.x(): .2f}, {self.top_left.y(): .2f}')
            self.top_left_coords.setPos(self.top_left)   
            if self.bottom_right is not None:
                self.setRect(QtCore.QRectF(self.top_left, self.bottom_right))
                 
        elif name == 'bottom_right' and self.bottom_right is not None:
            self.bottom_right = self.mapFromScene(pos)
            self.setRect(QtCore.QRectF(self.top_left, self.bottom_right))
            
            self.bottom_right_coords.setPlainText(f'{self.bottom_right.x(): .2f}, {self.bottom_right.y(): .2f}')
            self.bottom_right_coords.setPos(self.bottom_right)
            
        if self.top_left is not None and self.bottom_right is not None:
            tlx, tly, brx, bry = self.top_left.x(), self.top_left.y(), self.bottom_right.x(), self.bottom_right.y()
            self.size_text.setPlainText(f'{(brx - tlx): .2f} X {(bry - tly): .2f}')
            self.size_text.setPos((tlx + brx) // 2 - 50, (tly + bry) // 2)
            
    def moveItem(self):
        
        self.top_left_item.setEnabled(False)
        self.top_left_item.setPos(self.mapToScene(self.rect().topLeft()))
        self.top_left_item.setEnabled(True)
        self.bottom_right_item.setEnabled(False)
        self.bottom_right_item.setPos(self.mapToScene(self.rect().bottomRight()))
        self.bottom_right_item.setEnabled(True)
        
        self.top_left_coords.setPlainText(f'{self.top_left.x(): .2f}, {self.top_left.y(): .2f}')
        self.bottom_right_coords.setPlainText(f'{self.bottom_right.x(): .2f}, {self.bottom_right.y(): .2f}')
        
        if self.top_left is not None and self.bottom_right is not None:
            tlx, tly, brx, bry = self.top_left.x(), self.top_left.y(), self.bottom_right.x(), self.bottom_right.y()
            self.size_text.setPlainText(f'{(brx - tlx): .2f} X {(bry - tly): .2f}')
            self.size_text.setPos((tlx + brx) // 2 - 50, (tly + bry) // 2)

    def setPoint(self, pos):
        
        if self.top_left is not None:
            set_point = self.mapFromScene(pos)
            if set_point.x() >= self.top_left.x() and set_point.y() >= set_point.y():
                self.setRect(QtCore.QRectF(self.top_left, set_point))
        
            self.bottom_right_coords.setPlainText(f'{set_point.x(): .2f}, {set_point.y(): .2f}')
            self.bottom_right_coords.setPos(pos)
            
            tlx, tly, brx, bry = self.top_left.x(), self.top_left.y(), set_point.x(), set_point.y()
            self.size_text.setPlainText(f'{(brx - tlx): .2f} X {(bry - tly): .2f}')
            self.size_text.setPos((tlx + brx) // 2  - 50, (tly + bry) // 2)
                
    def itemChange(self, change, value):
        
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.moveItem()
        return super(RectangleAnnotation, self).itemChange(change, value)        
        
    def hoverEnterEvent(self, event):
        self.setBrush(QtGui.QColor(255, 0, 0, 100))
        super(RectangleAnnotation, self).hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QtGui.QBrush(QtCore.Qt.BrushStyle.NoBrush))
        super(RectangleAnnotation, self).hoverLeaveEvent(event)


class HomographyScene(QtWidgets.QGraphicsScene):
    
    def __init__(self, parent=None):
        
        super(HomographyScene, self).__init__(parent)
        
        self.image_item = QtWidgets.QGraphicsPixmapItem()
        self.image_item.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.CrossCursor))
        self.current_instruction = Instructions.No_Instruction
        self.addItem(self.image_item)
        self.point_item = None
        self.viewer = parent
        self.instruction = Instructions.No_Instruction
        self.current_mouse_coords = self.addText('', QtGui.QFont('Arial', 10, QtGui.QFont.Weight.Bold))
        self.current_mouse_coords.setDefaultTextColor(QtGui.QColor(255, 0, 0))
        self.current_mouse_coords.setPos(0, 0)
        self.point_items = defaultdict()
        self.point_id = 0

    def load_image(self, filename):
        self.image_item.setPixmap(QtGui.QPixmap(filename))
        self.setSceneRect(self.image_item.boundingRect())
    
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
            self.removeItem(self.point_items[self.point_id].point)
            self.removeItem(self.point_items[self.point_id])
            del self.point_items[self.point_id]
            self.point_id -= 1
    
    def mousePressEvent(self, event):
        
        if self.current_instruction == Instructions.Point_Instruction:
            if self.point_item.point is None:
                self.point_item.setPoint(event.scenePos(), self.point_id - 1)
                self.point_item.set = True
                self.setCurrentInstruction(Instructions.No_Instruction)
        
        return super(HomographyScene, self).mousePressEvent(event)
   
    def savePoints(self):
        pass

    def mouseMoveEvent(self, event):
        
        self.current_mouse_coords.setPlainText(f'{event.scenePos().x(): .1f}, {event.scenePos().y(): .1f}')
        self.current_mouse_coords.setPos(event.scenePos().x(), event.scenePos().y())

        super(HomographyScene, self).mouseMoveEvent(event)
        
class AnnotationScene(QtWidgets.QGraphicsScene):
    
    def __init__(self, parent=None):
        
        super(AnnotationScene, self).__init__(parent)
        
        self.image_item = QtWidgets.QGraphicsPixmapItem()
        self.image_item.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.CrossCursor))
        self.addItem(self.image_item)
        self.rectangle_item = None
        self.file = 'roi.json'
        self.current_instruction = Instructions.No_Instruction
        self.current_mouse_coords = self.addText('', QtGui.QFont('Arial', 30, QtGui.QFont.Weight.Bold))
        self.current_mouse_coords.setDefaultTextColor(QtGui.QColor(255, 0, 0))
        self.current_mouse_coords.setPos(0, 0)
        self.rectangle_items = list()
        self.polygon_id = 0
    
    def load_image(self, filename):
        self.image_item.setPixmap(QtGui.QPixmap(filename))
        self.setSceneRect(self.image_item.boundingRect())
     
    def deleteLastRectangle(self):
        
        if len(self.rectangle_items) > 0:
            
            self.removeItem(self.rectangle_items[-1].top_left_item)
            self.removeItem(self.rectangle_items[-1].bottom_right_item)
            self.removeItem(self.rectangle_items[-1])
            del self.rectangle_items[-1]
            self.polygon_id -= 1
    
    def saveRectangle(self):
        roi_dict = dict()
        print(len(self.rectangle_items))
        for i, rectangle_item in enumerate(self.rectangle_items):
            roi_dict[i] = rectangle_item.points

        with open(self.file, 'w') as f:
            json.dump(roi_dict, f)

    def setCurrentInstruction(self, instruction):
        
        if instruction == Instructions.No_Instruction and self.rectangle_item is not None:
            self.rectangle_items.append(self.rectangle_item)
            self.rectangle_item = None

        self.current_instruction = instruction
        
        if instruction == Instructions.Rectangle_Instruction:
            self.rectangle_item = RectangleAnnotation()
            self.addItem(self.rectangle_item)
            self.polygon_id += 1
            
    def mousePressEvent(self, event):
        if self.current_instruction == Instructions.Rectangle_Instruction:
            if self.rectangle_item.top_left is None or self.rectangle_item.bottom_right is None:
                if self.rectangle_item.top_left is None:
                    self.rectangle_item.setTopLeft(event.scenePos())
                else:
                    self.rectangle_item.setBottomRight(event.scenePos())
                    
        return super(AnnotationScene, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        
        if self.current_instruction == Instructions.No_Instruction:
            self.current_mouse_coords.setPlainText(f'{event.scenePos().x(): .2f}, {event.scenePos().y(): .2f}')
            self.current_mouse_coords.setPos(event.scenePos().x(), event.scenePos().y())
        
        if self.current_instruction == Instructions.Rectangle_Instruction:
            
            self.current_mouse_coords.setPlainText('')
            self.current_mouse_coords.setPos(0, 0)
            
            if self.rectangle_item.top_left is None or self.rectangle_item.bottom_right is None:
                self.rectangle_item.setPoint(event.scenePos())
            
        super(AnnotationScene, self).mouseMoveEvent(event)


class AnnotationView(QtWidgets.QGraphicsView):

    def __init__(self, parent=None):
        super(AnnotationView, self).__init__(parent)
        
        self.setRenderHints(QtGui.QPainter.RenderHint.Antialiasing | QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        self.setMouseTracking(True)
    

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
            self.fitInView(self.zoomStack[-1], Qt.AspectRatioMode.IgnoreAspectRatio)  # Show zoomed rect (ignore aspect ratio).
        else:
            self.zoomStack = []  # Clear the zoom stack (in case we got here because of an invalid zoom).
            self.fitInView(self.sceneRect(), self.aspectRatioMode)  # Show entire image (use current aspect ratio mode).
   
    def mousePressEvent(self, event):
        
        if event.button() == Qt.MouseButton.RightButton:
            scenePos = self.mapToScene(event.pos())
            self.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
            self.rightMouseButtonPressed.emit(scenePos.x(), scenePos.y())
        
        super(HomographyViewer, self).mousePressEvent(event)
        
    def mouseReleaseEvent(self, event):
        
        super(HomographyViewer, self).mouseReleaseEvent(event)
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

class AnnotationWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super(AnnotationWindow, self).__init__(parent)

        self.imagePlane = HomographyViewer(self)
        self.groundPlane = HomographyViewer(self)

        self.imageLayout = QHBoxLayout()
        self.imageLayout.setContentsMargins(0, 0, 0, 0)
        self.imageLayout.addWidget(self.imagePlane)
        self.imageLayout.addWidget(self.groundPlane)

        # Create Menus
        self.create_menus()

        self.buttonMainLayout = QVBoxLayout()
        
        
        self.deleteLastPointButtonImage = QPushButton()
        self.deleteLastPointButtonImage.setText('Delete Last Point - Image Plane')
        self.deleteLastPointButtonImage.clicked.connect(partial(self.actionDeleteLastPoint, self.imagePlane))
         
        self.deleteLastPointButtonGround = QPushButton()
        self.deleteLastPointButtonGround.setText('Delete Last Point - Ground Plane')
        self.deleteLastPointButtonGround.clicked.connect(partial(self.actionDeleteLastPoint, self.groundPlane))
        
        self.saveRectangleButton = QPushButton()
        self.saveRectangleButton.setText('Save Progress')
        self.saveRectangleButton.clicked.connect(self.actionSaveProgress)

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.setContentsMargins(0, 0, 0, 0)
        self.buttonLayout.addWidget(self.deleteLastRectangleButton)
        self.buttonLayout.addWidget(self.saveRectangleButton)
        
        self.mainLayout = QVBoxLayout()
        self.mainLayout.addLayout(self.imageLayout)
        self.mainLayout.addLayout(self.buttonLayout)
        
        QtGui.QShortcut(QtCore.Qt.Key.Key_T, self, activated=partial(self.m_scene.setCurrentInstruction, Instructions.Point_Instruction))
        QtGui.QShortcut(QtCore.Qt.Key.Key_Escape, self, activated=partial(self.m_scene.setCurrentInstruction, Instructions.No_Instruction))

        wid = QWidget()
        self.setCentralWidget(wid)
        wid.setLayout(self.mainLayout)
        
        
    def actionDeleteLastPoint(self, view):
        
        view.scene.deleteLastPoint()
        
    def actionSaveProgress(self):
        
        self.m_scene.saveRectangle()

    def create_menus(self):
        menu_file = self.menuBar().addMenu("File")
        load_image_action = menu_file.addAction("&Load Image")
        load_image_action.triggered.connect(self.load_image)

        menu_instructions = self.menuBar().addMenu("Intructions")
        polygon_action = menu_instructions.addAction("Point")
        polygon_action.triggered.connect(partial(self.m_scene.setCurrentInstruction, Instructions.Point_Instruction))

    @QtCore.pyqtSlot()
    def load_image(self):
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(self, 
            "Open Image",
            QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.StandardLocation.PicturesLocation), #QtCore.QDir.currentPath(), 
            "Image Files (*.png *.jpg *.bmp)")
        
        if filename:
            self.m_scene.load_image(filename)
            self.m_view.fitInView(self.m_scene.image_item, QtCore.Qt.AspectRatioMode.KeepAspectRatio)
            self.m_view.centerOn(self.m_scene.image_item)

# Make annotation viewer





if __name__ == '__main__':
    import sys

    app = QtWidgets.QApplication(sys.argv)
    w = AnnotationWindow()
   
    w.showMaximized()
    sys.exit(app.exec())