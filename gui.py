#!/usr/bin/env python

#Skype Log Viewer: A simple http server that publishes human readable skype logs
#Copyright (C) 2011 Horacio Duran <hduran@machinalis.com>

#This program is free software: you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation, either version 3 of the License, or
#(at your option) any later version.

#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU General Public License
#along with this program.  If not, see <http://www.gnu.org/licenses/>.

# This is a shorter version of
# http://www.diegosarmentero.com/2010/03/navegador-web-en-63-lineas-de-codigo.html
# From Diego Sarmentero, many thanks to him

import sys, re, SocketServer
from PyQt4 import QtGui, QtCore, QtWebKit
import skypelogviewer
import thread

class PyBrowser(QtGui.QWidget):

    def __init__(self, base_url):

        QtGui.QWidget.__init__(self)
        self.setWindowTitle('Simple Web Browser')

        v_box = QtGui.QVBoxLayout(self)
        #Navigation Bar

        #Page Frame
        self.web = QtWebKit.QWebView()
        self.web.load(QtCore.QUrl(base_url))
        #Status Bar
        self.status = QtGui.QStatusBar()
        self.prog = QtGui.QProgressBar()
        self.load = QtGui.QLabel('Loading...')
        self.status.addWidget(self.load)
        self.status.addWidget(self.prog)

        #Add widgets and layout to window
        v_box.addWidget(self.web)
        v_box.addWidget(self.status)

        self.connect(self.web, QtCore.SIGNAL("loadProgress(int)"), self.progress)
        self.connect(self.web, QtCore.SIGNAL("loadFinished(bool)"), self.loadComplete)
        self.connect(self.web, QtCore.SIGNAL("loadStarted()"), self.status.show)
        self.connect(self, QtCore.SIGNAL("destroyed()"), self.close)

        self.httpd = SocketServer.TCPServer(("", PORT), skypelogviewer.SkypeLogHandler)
        self.thandler = thread.start_new_thread(self.httpd.serve_forever, tuple())

    def closeEvent(self, event):
        #import pdb; pdb.set_trace()
        self.httpd.server_close()
        return QtGui.QWidget.closeEvent(self, event)

    def progress(self, porc):
        self.prog.setValue(porc)

    def loadComplete(self):
        self.status.hide()


if __name__ == '__main__':
    app = QtGui.QApplication(sys.argv)
    PORT = 8699
    pybrowser = PyBrowser('http://localhost:%s' % PORT)
    pybrowser.show()
    sys.exit(app.exec_())