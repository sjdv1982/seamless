#!/usr/bin/env python3 

import sys 

from PyQt5.QtWebEngineWidgets import QWebEngineView 
from PyQt5.QtWidgets import QApplication 
from PyQt5.QtCore import QUrl 

app = QApplication(sys.argv) 

browser = QWebEngineView() 
browser.load(QUrl(sys.argv[1])) 
browser.show() 

app.exec_() 
