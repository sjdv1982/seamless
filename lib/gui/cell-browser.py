from seamless.qt.QtWebEngineWidgets import QWebEngineView
from seamless.qt import QtWidgets, QtGui

widget = QWebEngineView()
widget.setWindowTitle(PINS.title.get())
reloadAction = QtWidgets.QAction(QtGui.QIcon('exit.png'), '&Exit', widget)
reloadAction.setShortcut('F5')
reloadAction.setStatusTip('Reload')
reloadAction.triggered.connect(widget.reload)
widget.addAction(reloadAction)
widget.setHtml(PINS.value.get())
widget.show()
