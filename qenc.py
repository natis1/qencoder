#!/usr/bin/python3
# This Python file uses the following encoding: utf-8
import qencoder
from qencoder.window import window
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QApplication

import sys
import multiprocessing
import os

#baseUIClass, baseUIWidget = uic.loadUiType("mainwindow.ui")

def main():
    if not sys.platform.startswith('win'):
        os.setpgrp()
    global window
    if sys.platform.startswith('win'):
        multiprocessing.freeze_support()
    print("Loading program... please wait!")
    app = QtWidgets.QApplication(sys.argv)
    window = window()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
