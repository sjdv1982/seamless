import os, sys
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.Qt import QUrl
from PyQt5 import QtWidgets, QtGui
from PyQt5.QtWidgets import QApplication

app = QApplication(sys.argv)

widget = QWebEngineView()
#fake_url = QUrl.fromLocalFile(os.path.abspath("seamless.html"))
widget.setWindowTitle("Test")
reloadAction = QtWidgets.QAction(QtGui.QIcon('exit.png'), '&Reload', widget)
reloadAction.setShortcut('F5')
reloadAction.setStatusTip('Reload')
reloadAction.triggered.connect(widget.reload)
widget.addAction(reloadAction)
widget.setHtml(open("plotly-start.html").read())
widget.show()

app.exec_()