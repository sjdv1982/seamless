import os
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.Qt import QUrl
from PyQt5 import QtWidgets, QtGui

widget = QWebEngineView()
fake_url = QUrl.fromLocalFile(os.path.abspath("seamless.html"))
widget.setWindowTitle(PINS.title.get().data)
reloadAction = QtWidgets.QAction(QtGui.QIcon('exit.png'), '&Reload', widget)
reloadAction.setShortcut('F5')
reloadAction.setStatusTip('Reload')
reloadAction.triggered.connect(widget.reload)
widget.addAction(reloadAction)
widget.setHtml(PINS.val.get().data, fake_url)
widget.show()
