from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QLabel, QPlainTextEdit
from PyQt5.QtGui import QPainter, QPixmap, QPen
class Panel(QWidget):
    def __init__(self, parent):
        QLabel.__init__(self, parent)
    def paintEvent(self, e):
        super().paintEvent(e)
        qp = QPainter()
        qp.begin(self)
        line_numbers = (3,5,6,14)
        try:
            qp.setBrush(QtGui.QColor("#D0D0D0"))
            qp.drawRect(0,0,self.width(), self.height())
            qp.setBrush(Qt.red)
            x = self.parent().margin / 2
            for top, bottom, line_number, block in self.parent().visible_blocks:
                if line_number in line_numbers:
                    mid = (bottom + top)/2
                    radius = (bottom - top) / 2
                    qp.drawEllipse(x-0.5*radius, mid-0.5*radius, radius, radius)
        finally:
            qp.end()


class CodeEditor(QPlainTextEdit):
    margin = 50
    def __init__(self):
        super().__init__()
        self.panel = Panel(self)
        self.visible_blocks = []
        #self.panel.show()

    def update_visible_blocks(self, event):
        """Update the list of visible blocks/lines position"""
        #from Spyder prpject
        self.visible_blocks[:] = []
        block = self.firstVisibleBlock()
        blockNumber = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(
            self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        ebottom_top = 0
        ebottom_bottom = self.height()

        while block.isValid():
            visible = (top >= ebottom_top and bottom <= ebottom_bottom)
            if not visible:
                break
            if block.isVisible():
                self.visible_blocks.append((top, bottom, blockNumber+1, block))
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            blockNumber = block.blockNumber()

    def resizeEvent(self, e):
        #print(e.size())
        super().resizeEvent(e)
        crect = self.contentsRect()
        self.viewport().setGeometry(
          crect.left() + self.margin,
          crect.top(),
          crect.width() - self.margin,
          crect.height()
        )
        self.panel.setGeometry(
            crect.left(),
            crect.top(),
            self.margin,
            crect.height(),
        )

    def paintEvent(self, e):
        self.update_visible_blocks(e)
        #print(self.visible_blocks[0][2])
        self.panel.repaint()
        super().paintEvent(e)

        #self.panel.paintEvent(e)
        #print("PAINT!")


widget = CodeEditor()
widget.setGeometry(0, 100, 300,200)
widget.zoomIn(10)
widget.show()
widget.setPlainText("\n".join([str(v) for v in range(10,1000,10)]))
