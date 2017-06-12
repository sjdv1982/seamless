#!/usr/bin/env python3 

import sys, os 

from PyQt5.QtWebEngineWidgets import QWebEngineView 
from PyQt5.QtWidgets import QApplication 
from PyQt5.QtCore import QUrl 

app = QApplication(sys.argv) 
fake_url = QUrl.fromLocalFile(os.path.abspath("plotly-start.html"))
browser = QWebEngineView() 
#browser.load(QUrl(sys.argv[1])) 
browser.load(fake_url)
browser.show() 

app.exec_() 
