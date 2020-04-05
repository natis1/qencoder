#!/bin/python3
# This Python file uses the following encoding: utf-8
from PyQt5 import QtCore, QtWidgets, uic, QtGui
from PyQt5.QtWidgets import QInputDialog, QFileDialog, QApplication, QMainWindow, QSpinBox, QCheckBox
from functools import partial

import sys
from mainwindow import Ui_MainWindow

from pav1n import Av1an

import multiprocessing

from types import SimpleNamespace
from pathlib import Path
import os

#baseUIClass, baseUIWidget = uic.loadUiType("mainwindow.ui")

class window(QMainWindow, Ui_MainWindow):
    def __init__(self, *args, **kwargs):
        QMainWindow.__init__(self, *args, **kwargs)
        self.setupUi(self)
        self.inputFileChoose.clicked.connect(self.inputFileSelect)
        self.outputFileChoose.clicked.connect(self.outputFileSelect)
        self.label_audio.setEnabled(0)
        self.spinBox_quality.setValue(30)
        enable_slot = partial(self.audioEnableState, self.checkBox_audio)
        disable_slot = partial(self.audioDisableState, self.checkBox_audio)
        self.checkBox_audio.stateChanged.connect(lambda x: enable_slot() if x else disable_slot())

        enable_slot2 = partial(self.bitrateEnableState, self.checkBox_bitrate)
        disable_slot2 = partial(self.bitrateDisableState, self.checkBox_bitrate)
        self.checkBox_bitrate.stateChanged.connect(lambda x: enable_slot2() if x else disable_slot2())
        self.pushButton.clicked.connect(self.encodeVideo)


    def inputFileSelect(self):
        filename = QFileDialog.getOpenFileName()
        self.inputPath.setText(filename[0])
        if ( len(self.outputPath.text() ) > 1 ):
            self.pushButton.setEnabled(1)

    def outputFileSelect(self):
        filename = QFileDialog.getSaveFileName()
        if ( filename[0].endswith(".mkv") or filename[0].endswith(".webm") ):
            self.outputPath.setText(filename[0])
        else :
            self.outputPath.setText(filename[0] + ".mkv")
        if ( len(self.inputPath.text()) > 1 ):
            self.pushButton.setEnabled(1)

    def audioEnableState(self, checkbox):
        self.label_audio.setEnabled(1)
        self.spinBox_audio.setReadOnly(0)

    def audioDisableState(self, checkbox):
        self.label_audio.setEnabled(0)
        self.spinBox_audio.setReadOnly(1)

    def bitrateEnableState(self, checkbox):
        self.label_q.setText("Bitrate (kbps)")
        self.spinBox_quality.setMaximum(99999)
        self.spinBox_quality.setMinimum(8)
        self.spinBox_quality.setValue(3000)
        self.spinBox_boost.setReadOnly(1)
        self.label_boost.setEnabled(0)

    def bitrateDisableState(self, checkbox):
        self.label_q.setText("Q factor")
        self.spinBox_quality.setMaximum(50)
        self.spinBox_quality.setMinimum(0)
        self.spinBox_quality.setValue(30)
        self.spinBox_boost.setReadOnly(0)
        self.label_boost.setEnabled(1)

    def encodeVideo(self):
        self.pushButton.setEnabled(0)
        self.progressBar_status.setEnabled(1)
        self.progressBar_total.setEnabled(1)
        self.spinBox_audio.setEnabled(0)
        self.spinBox_quality.setEnabled(0)
        self.spinBox_boost.setEnabled(0)
        self.spinBox_speed.setEnabled(0)
        self.spinBox_split.setEnabled(0)
        self.spinBox_jobs.setEnabled(0)
        self.label_jobs.setEnabled(0)
        self.inputFileChoose.setEnabled(0)
        self.outputFileChoose.setEnabled(0)
        self.label_2.setEnabled(0)
        self.label_audio.setEnabled(0)
        self.label_boost.setEnabled(0)
        self.label_q.setEnabled(0)
        self.label_split.setEnabled(0)
        self.label_status.setEnabled(1)
        self.label_status.setText("Initializing...")
        multiprocessing.freeze_support()
        #Args = recordclass('Args', ['video_params', 'file_path', 'encoder', 'workers', 'audio_params', 'threshold',
        #'temp', 'logging', 'passes', 'output_file', 'ffmpeg', 'pix_format', 'scenes', 'resume', 'no_check', 'keep', 'boost', 'br', 'bl'])
        args = SimpleNamespace(video_params = '', file_path = Path(self.inputPath.text()), encoder = 'aom', workers = self.spinBox_jobs.value(), audio_params = '', threshold = self.spinBox_split.value(),
        temp = Path(os.path.abspath("temp")), logging = None, passes = 2, output_file = Path(self.outputPath.text()), ffmpeg = None, pix_format = "yuv420p", scenes = None, resume = False, no_check = False, keep = False,
        boost = False, br = 0, bl = 0)
        if (self.checkBox_audio.isChecked()):
            args.audio_params = "-b:a " + str(self.spinBox_audio.value()) + " -c:a libopus"
        else :
            args.audio_params = "-c:a copy"

        if (self.checkBox_bitrate.isChecked()):
            args.video_params = " --end-usage=vbr --threads=4 --tile-columns=2 --tile-rows=1 --cpu-used=" + str(self.spinBox_speed.value()) + " --target-bitrate=" + str(self.spinBox_quality.value())
            args.boost = False
            args.br = 0
            args.bl = 0
        elif (self.spinBox_boost.value() < 1) :
            args.video_params = " --end-usage=q --threads=4 --tile-columns=2 --tile-rows=1 --cpu-used=" + str(self.spinBox_speed.value()) + " --cq-level=" + str(self.spinBox_quality.value())
            args.boost = False
            args.br = 0
            args.bl = 0
        else :
            args.video_params = " --end-usage=q --threads=4 --tile-columns=2 --tile-rows=1 --cpu-used=" + str(self.spinBox_speed.value()) + " --cq-level=" + str(self.spinBox_quality.value())
            args.boost = True
            args.bl = 0
            args.br = self.spinBox_boost.value()

        if (self.checkBox_hdr.isChecked()):
            args.video_params = args.video_params + " --bit-depth=10 "
        else :
            args.video_params = args.video_params + " --bit-depth=8 "
        av1an = Av1an(args)
        av1an.setup_routine(self.progressBar_status, self.progressBar_total, self.label_status)
        files = av1an.get_video_queue(args.temp / 'split') # progressBarMini, progressBarMain, progressLabel

        # Make encode queue
        commands = av1an.compose_encoding_queue(files)

        av1an.encoding_loop(commands, self.progressBar_status, self.progressBar_total, self.label_status)

        av1an.concatenate_video(self.progressBar_status, self.progressBar_total, self.label_status)
        self.progressBar_total.setValue(100)
        self.label_status.setText("Completed")


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = window()
    window.show()
    sys.exit(app.exec_())
