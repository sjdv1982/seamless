from seamless.qt.QtWidgets import QTextEdit, QMainWindow, QAction
from seamless.qt.QtCore import Qt
from PyQt5.QtGui import QColor

w = QMainWindow()
#w.setWindowFlags(Qt.WindowStaysOnTopHint)
w.setAttribute(Qt.WA_ShowWithoutActivating)
w.resize(600,600)
w.setWindowTitle(PINS.title.get())

class MyTextEdit(QTextEdit):
    def focusOutEvent(self, event):
        PINS.value.set(self.toPlainText())
        QTextEdit.focusOutEvent(self, event)

w.show()
b = MyTextEdit()
b.setFontPointSize(15)
w.setCentralWidget(b)

saveAction = QAction('&Save', w)
saveAction.setShortcut('Ctrl+S')
saveAction.setStatusTip('Save')
saveAction.triggered.connect(lambda: PINS.value.set(b.toPlainText()))
w.menuBar().addAction(saveAction)

if PINS.value.defined:
    b.setText(PINS.value.get())
#b.setFontItalic(True)
#b.setTextColor(QColor(255,0,0))
