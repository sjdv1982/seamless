import os
from seamless.qt.QtWebEngineWidgets import QWebEngineView
from seamless.qt.Qt import QUrl
from seamless.qt import QtWidgets, QtGui

widget = QWebEngineView()
fake_url = QUrl.fromLocalFile(os.path.abspath("seamless.html"))
widget.setWindowTitle(PINS.title.get())
reloadAction = QtWidgets.QAction(QtGui.QIcon('exit.png'), '&Reload', widget)
reloadAction.setShortcut('F5')
reloadAction.setStatusTip('Reload')
reloadAction.triggered.connect(widget.reload)
widget.addAction(reloadAction)
widget.setHtml(PINS.value.get(), fake_url)
widget.show()
