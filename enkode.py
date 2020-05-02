#!/bin/python3
# This Python file uses the following encoding: utf-8
from PyQt5 import QtCore, QtWidgets, uic, QtGui
from PyQt5.QtWidgets import QInputDialog, QFileDialog, QApplication, QMainWindow, QSpinBox, QCheckBox
from functools import partial

import sys
from mainwindow import Ui_MainWindow

from pav1n import Av1an

import multiprocessing
from threading import Thread

from types import SimpleNamespace
from pathlib import Path
import os

#baseUIClass, baseUIWidget = uic.loadUiType("mainwindow.ui")

class window(QMainWindow, Ui_MainWindow):
    twopassState = True
    realtimeState = False
    qualityState = 3
    audioState = 4
    runningEncode = False

    def __init__(self, *args, **kwargs):
        QMainWindow.__init__(self, *args, **kwargs)
        self.setupUi(self)
        self.inputFileChoose.clicked.connect(self.inputFileSelect)
        self.outputFileChoose.clicked.connect(self.outputFileSelect)
        self.label_audio.setEnabled(0)
        self.spinBox_quality.setValue(28)
        enable_slot = partial(self.audioEnableState, self.checkBox_audio)
        disable_slot = partial(self.audioDisableState, self.checkBox_audio)
        self.checkBox_audio.stateChanged.connect(lambda x: enable_slot() if x else disable_slot())

        enable_slot2 = partial(self.bitrateEnableState, self.checkBox_bitrate)
        disable_slot2 = partial(self.bitrateDisableState, self.checkBox_bitrate)
        self.checkBox_bitrate.stateChanged.connect(lambda x: enable_slot2() if x else disable_slot2())

        self.pushButton.clicked.connect(self.encodeVideo)
        self.audioqualitybox.addItem("Ultra Low (opus 24kbps")
        self.audioqualitybox.addItem("Low (opus 32kbps)")
        self.audioqualitybox.addItem("Medium (opus 64kbps)")
        self.audioqualitybox.addItem("High (opus 76kbps)")
        self.audioqualitybox.addItem("Very High (opus 96kbps)")
        self.audioqualitybox.addItem("Transparent (opus 128kbps)")
        self.audioqualitybox.addItem("Placebo (opus 160kbps)")
        self.audioqualitybox.addItem("Insane (opus 256kbps)")
        self.audioqualitybox.addItem("Custom")
        self.audioqualitybox.setCurrentIndex(4)
        self.audioqualitybox.activated[int].connect(self.changeAudioPreset)

        self.comboBox_quality.addItem("Ultra low (q 40)")
        self.comboBox_quality.addItem("Very low (q 36)")
        self.comboBox_quality.addItem("Low (q 32)")
        self.comboBox_quality.addItem("Medium (q 28)")
        self.comboBox_quality.addItem("Good (q 26)")
        self.comboBox_quality.addItem("Very Good (q 24)")
        self.comboBox_quality.addItem("Amazing (q 20)")
        self.comboBox_quality.addItem("Effectively Lossless (q 10)")
        self.comboBox_quality.addItem("Lossless (q 0)")
        self.comboBox_quality.addItem("Custom")
        self.comboBox_quality.setCurrentIndex(3)
        self.comboBox_quality.activated[int].connect(self.changeQPreset)

        self.presetbox.addItem("Ultra fast")  # cpu-used 8, rt
        self.presetbox.addItem("Super fast")  # cpu-used 7, rt
        self.presetbox.addItem("Faster")  # cpu-used 6, good
        self.presetbox.addItem("Fast")  # cpu-used 5, good
        self.presetbox.addItem("Medium")  # cpu-used 4, good
        self.presetbox.addItem("Slow")  # cpu-used 3, good
        self.presetbox.addItem("Slower")  # cpu-used 2, good
        self.presetbox.addItem("Very slow")  # cpu-used 1, good
        self.presetbox.addItem("Placebo")  # cpu-used 0, good
        self.presetbox.setCurrentIndex(4)
        self.presetbox.activated[int].connect(self.changePresetSimple)

        self.comboBox_colorspace.addItem("Auto (recommended)")
        self.comboBox_colorspace.addItem("bt709")
        self.comboBox_colorspace.addItem("bt601")
        self.comboBox_colorspace.addItem("bt2020-10b ncl")
        self.comboBox_colorspace.addItem("bt2020-10b cl")
        self.comboBox_colorspace.addItem("Custom")
        self.comboBox_colorspace.activated[int].connect(self.changeColorspace)

        self.comboBox_inputFormat.addItem("yuv420p")
        self.comboBox_inputFormat.addItem("yuv420p10le")
        self.comboBox_inputFormat.addItem("yuv420p12le")
        self.comboBox_inputFormat.addItem("yuv422p")
        self.comboBox_inputFormat.addItem("yuv422p10le")
        self.comboBox_inputFormat.addItem("yuv422p12le")
        self.comboBox_inputFormat.addItem("yuv444p")
        self.comboBox_inputFormat.addItem("yuv444p10le")
        self.comboBox_inputFormat.addItem("yuv444p12le")

        self.audioqualitybox.setEnabled(0)
        self.label_audioquality.setEnabled(0)
        self.spinBox_speed.valueChanged.connect(self.changePresetAdvanced)
        self.spinBox_quality.valueChanged.connect(self.customQPreset)
        self.spinBox_audio.valueChanged.connect(self.customAPreset)
        self.checkBox_rtenc.stateChanged.connect(self.changeRTState)
        self.actionOpen.triggered.connect(self.inputFileSelect)
        self.actionSave.triggered.connect(self.outputFileSelect)
        self.actionExit.triggered.connect(self.quitProgram)
        # self.speedButton.changeEvent.connect(self.setSpeed)

    def quitProgram(self):
        sys.exit(0)

    def changeColorspace(self, newspace):
        colorInfo = self.getColorspace(newspace)
        self.lineEdit_colordata.setText(colorInfo)
        if (newspace == 5):
            self.lineEdit_colordata.setEnabled(1)
        else:
            self.lineEdit_colordata.setEnabled(0)

    def getColorspace(self, inputSpace):
        if (inputSpace == 0):
            return ""
        elif (inputSpace == 1):
            return "--color-primaries=bt709 --transfer-characteristics=bt709 --matrix-coefficients=bt709"
        elif (inputSpace == 2):
            return "--color-primaries=bt601 --transfer-characteristics=bt601 --matrix-coefficients=bt601"
        elif (inputSpace == 3):
            return "--color-primaries=bt2020 --transfer-characteristics=bt2020-10bit --matrix-coefficients=bt2020ncl"
        elif (inputSpace == 4):
            return "--color-primaries=bt2020 --transfer-characteristics=bt2020-10bit --matrix-coefficients=bt2020cl"
        else:
            return self.lineEdit_colordata.text()

    def changeRTState(self, newState):
        if (newState):
            if (self.checkBox_twopass.isEnabled()):
                self.twopassState = self.checkBox_twopass.isChecked()
            self.checkBox_twopass.setChecked(0)
            self.checkBox_twopass.setEnabled(0)
        else:
            self.checkBox_twopass.setChecked(self.twopassState)
            self.checkBox_twopass.setEnabled(1)

    def customAPreset(self):
        self.audioqualitybox.setCurrentIndex(7)  # custom

    def changeAudioPreset(self, i):
        self.audioState = i
        trueQuality = self.getAudioBitrate(i)
        print(str(trueQuality) + " is current quality")
        self.spinBox_audio.setValue(trueQuality)
        self.audioqualitybox.setCurrentIndex(i)

    def customQPreset(self):
        self.comboBox_quality.setCurrentIndex(9)  # custom

    def changeQPreset(self, i):
        trueQuality = self.getQuality(i)
        self.spinBox_quality.setValue(trueQuality)
        self.qualityState = i
        self.comboBox_quality.setCurrentIndex(i)

    def changePresetAdvanced(self):
        if (self.spinBox_speed.value() > 6):
            if (self.checkBox_rtenc.isEnabled()):
                self.realtimeState = self.checkBox_rtenc.isChecked()
            if (self.checkBox_twopass.isEnabled()):
                self.twopassState = self.checkBox_twopass.isChecked()
            self.checkBox_twopass.setChecked(0)
            self.checkBox_twopass.setEnabled(0)
            self.checkBox_rtenc.setChecked(1)
            self.checkBox_rtenc.setEnabled(0)
        else:
            if (self.checkBox_rtenc.isEnabled()):
                self.realtimeState = self.checkBox_rtenc.isChecked()
            if (self.checkBox_twopass.isEnabled()):
                self.twopassState = self.checkBox_twopass.isChecked()
            self.checkBox_twopass.setChecked(self.twopassState)
            self.checkBox_twopass.setEnabled(1)
            self.checkBox_rtenc.setEnabled(1)
            self.checkBox_rtenc.setChecked(self.realtimeState)
        self.presetbox.setCurrentIndex(8 - self.spinBox_speed.value())

    def changePresetSimple(self, i):
        if (i <= 1):
            if (self.checkBox_rtenc.isEnabled()):
                self.realtimeState = self.checkBox_rtenc.isChecked()
            if (self.checkBox_twopass.isEnabled()):
                self.twopassState = self.checkBox_twopass.isChecked()
            self.checkBox_twopass.setChecked(0)
            self.checkBox_twopass.setEnabled(0)
            self.checkBox_rtenc.setEnabled(0)
            self.checkBox_rtenc.setChecked(1)
        else:
            if (self.checkBox_rtenc.isEnabled()):
                self.realtimeState = self.checkBox_rtenc.isChecked()
            if (self.checkBox_twopass.isEnabled()):
                self.twopassState = self.checkBox_twopass.isChecked()
            self.checkBox_twopass.setChecked(self.twopassState)
            self.checkBox_twopass.setEnabled(1)
            self.checkBox_rtenc.setEnabled(1)
            self.checkBox_rtenc.setChecked(self.realtimeState)
        self.spinBox_speed.setValue(8 - i)

    def setSpeed(self):
        print("Speed set to ")

    def getAudioBitrate(self, iindex):
        if (iindex == 0):
            return 24
        elif (iindex == 1):
            return 32
        elif (iindex == 2):
            return 64
        elif (iindex == 3):
            return 76
        elif (iindex == 4):
            return 96
        elif (iindex == 5):
            return 128
        elif (iindex == 6):
            return 160
        elif (iindex == 7):
            return 256
        return self.spinBox_audio.value()

    def getQuality(self, qval):
        if (qval == 0):
            return 40
        elif (qval == 1):
            return 36
        elif (qval == 2):
            return 32
        elif (qval == 3):
            return 28
        elif (qval == 4):
            return 26
        elif (qval == 5):
            return 24
        elif (qval == 6):
            return 20
        elif (qval == 7):
            return 10
        elif (qval == 8):
            return 0
        return self.spinBox_quality.value()

    def inputFileSelect(self):
        filename = QFileDialog.getOpenFileName(filter = "Videos(*.mp4 *.mkv *.webm *.flv *.gif *.3gp *.wmv *.avi);;All(*)")
        self.inputPath.setText(filename[0])
        if (len(self.outputPath.text()) > 1):
            self.pushButton.setEnabled(1)

    def outputFileSelect(self):
        filename = QFileDialog.getSaveFileName(filter = "mkv and webm videos(*.mkv *.webm)")
        if (filename[0].endswith(".mkv") or filename[0].endswith(".webm")):
            self.outputPath.setText(filename[0])
        elif (len(filename[0]) > 0):
            self.outputPath.setText(filename[0] + ".mkv")
        if (len(self.inputPath.text()) > 1):
            self.pushButton.setEnabled(1)

    def audioEnableState(self, checkbox):
        self.label_audio.setEnabled(1)
        self.spinBox_audio.setReadOnly(0)
        self.audioqualitybox.setEnabled(1)
        self.label_audioquality.setEnabled(1)
        self.spinBox_audio.setEnabled(1)

    def audioDisableState(self, checkbox):
        self.label_audio.setEnabled(0)
        self.spinBox_audio.setReadOnly(1)
        self.audioqualitybox.setEnabled(0)
        self.label_audioquality.setEnabled(0)
        self.spinBox_audio.setEnabled(0)

    def bitrateEnableState(self, checkbox):
        self.label_q.setText("Bitrate (kbps)")
        self.spinBox_quality.setMaximum(99999)
        self.spinBox_quality.setMinimum(8)
        self.spinBox_quality.setValue(3000)
        self.spinBox_boost.setReadOnly(1)
        self.label_boost.setEnabled(0)
        self.comboBox_quality.setCurrentIndex(9)  # custom
        self.comboBox_quality.setEnabled(0)
        self.label_quality.setEnabled(0)

    def bitrateDisableState(self, checkbox):
        self.label_q.setText("Q factor")
        self.spinBox_quality.setMaximum(50)
        self.spinBox_quality.setMinimum(0)
        self.spinBox_quality.setValue(30)
        self.spinBox_boost.setReadOnly(0)
        self.label_boost.setEnabled(1)
        self.comboBox_quality.setEnabled(1)
        self.label_quality.setEnabled(1)

    def encodeVideo(self):
        if (self.runningEncode):
            self.finalizeEncode()
            return
        self.pushButton.setEnabled(0)
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
        self.label_inputformat.setEnabled(0)
        self.label_6.setEnabled(0)
        self.comboBox_colorspace.setEnabled(0)
        self.comboBox_inputFormat.setEnabled(0)
        self.comboBox_quality.setEnabled(0)
        self.audioqualitybox.setEnabled(0)
        self.presetbox.setEnabled(0)
        self.checkBox_audio.setEnabled(0)
        self.checkBox_bitrate.setEnabled(0)
        self.checkBox_hdr.setEnabled(0)
        self.checkBox_minsplit.setEnabled(0)
        self.checkBox_resume.setEnabled(0)
        self.checkBox_rtenc.setEnabled(0)
        self.checkBox_tempfolder.setEnabled(0)
        self.checkBox_twopass.setEnabled(0)
        self.audioqualitybox.setEnabled(0)
        self.label_audioquality.setEnabled(0)
        self.label_preset.setEnabled(0)
        self.label_quality.setEnabled(0)

        self.label_status.setEnabled(1) # self.setupUi(self)
        self.label_status.setText("Initializing...")
        #multiprocessing.freeze_support()
        #Args = recordclass('Args', ['video_params', 'file_path', 'encoder', 'workers', 'audio_params', 'threshold',
        #'temp', 'logging', 'passes', 'output_file', 'ffmpeg', 'pix_format', 'scenes', 'resume', 'no_check', 'keep', 'boost', 'br', 'bl'])
        #args = SimpleNamespace(video_params = '', file_path = Path(self.inputPath.text()), encoder = 'aom', workers = self.spinBox_jobs.value(), audio_params = '', threshold = self.spinBox_split.value(),
        #args = {video_params: '', file_path: Path(self.inputPath.text()), encoder: 'aom', workers: self.spinBox_jobs.value(), audio_params: '', threshold = self.spinBox_split.value()
        #temp = Path(os.path.abspath("temp")), logging = None, passes = 2, output_file = Path(self.outputPath.text()), ffmpeg = None, pix_format = "yuv420p", scenes = None, resume = False, no_check = False, keep = False,
        #boost = False, br = 0, bl = 0)
        args = {'video_params': '', 'input_file': Path(self.inputPath.text()), 'encoder': 'aom',
                'workers' : self.spinBox_jobs.value(), 'audio_params': '',
                'threshold': self.spinBox_split.value(), 'temp': Path(os.path.abspath("temp")),
                'logging' : None, 'passes' : (2 if self.checkBox_twopass.isChecked() else 1),
                'output_file': Path(self.outputPath.text()), 'scenes' : None,
                'resume' : self.checkBox_resume.isChecked(), 'keep' : self.checkBox_tempfolder.isChecked(),
                'min_splits' : self.checkBox_minsplit.isChecked(), 'pix_format' : self.comboBox_inputFormat.currentText()
        }
        if (self.checkBox_audio.isChecked()):
            args['audio_params'] = "-b:a " + str(self.spinBox_audio.value()) + " -c:a libopus"
        else :
            args['audio_params'] = "-c:a copy"
        vparams = " --threads=4 --tile-columns=2 --tile-rows=1 --cpu-used=" + str(self.spinBox_speed.value())
        if (self.checkBox_rtenc.isChecked()):
            vparams += " --rt"
        else:
            vparams += " --good"
        if (self.checkBox_bitrate.isChecked()):
            vparams += " --end-usage=vbr --target-bitrate=" + str(self.spinBox_quality.value())
            args['boost'] = False
            args['br'] = 0
            args['bl'] = 0
        elif (self.spinBox_boost.value() < 1) :
            vparams += " --end-usage=q --cq-level=" + str(self.spinBox_quality.value())
            args['boost'] = False
            args['br'] = 0
            args['bl'] = 0
        else :
            vparams = " --end-usage=q --cq-level=" + str(self.spinBox_quality.value())
            args['boost'] = True
            args['bl'] = 0
            args['br'] = self.spinBox_boost.value()

        if (self.checkBox_hdr.isChecked()):
            vparams += " --bit-depth=10"
        else :
            vparams += " --bit-depth=8"
        #if (self.comboBox_inputFormat.currentIndex() <= 2):
        #    vparams += " --i420"
        #elif (self.comboBox_inputFormat.currentIndex() <= 5):
        #    vparams += " --i422"
        #else:
        #    vparams += " --i444"

        #if (self.comboBox_inputFormat.currentIndex() % 3 == 0):
        #    vparams += " --input-bit-depth=8"
        #elif (self.comboBox_inputFormat.currentIndex() % 3 == 0):
        #    vparams += " --input-bit-depth=10"
        #else:
        #    vparams += " --input-bit-depth=12"

        args['video_params'] = vparams
        print(args)
        thread = Thread(target = self.runProcessing, args = (args,))
        thread.start()

    def runProcessing(self, dictargs):
        self.runningEncode = True
        av1an = Av1an(dictargs)
        print(dictargs)
        av1an.main_thread(self)
        print("\n\nEncode completed for " + str(dictargs['input_file']) + " -> " + str(dictargs['output_file']))
        self.pushButton.setEnabled(1)
        self.pushButton.setStyleSheet("color: black; background-color: white")
        self.pushButton.setText("Finalize")
        self.progressBar_total.setEnabled(0)
        self.label_status.setText("Encoding complete!")

    def finalizeEncode(self):
        self.runningEncode = False
        self.pushButton.setText("Encode")
        self.checkBox_audio.setEnabled(1)
        self.spinBox_speed.setEnabled(1)
        self.spinBox_speed.setValue(self.spinBox_speed.value())
        self.spinBox_split.setEnabled(1)
        self.spinBox_jobs.setEnabled(1)
        self.label_jobs.setEnabled(1)
        self.inputFileChoose.setEnabled(1)
        self.outputFileChoose.setEnabled(1)
        self.inputPath.setText("")
        self.outputPath.setText("")
        self.label_2.setEnabled(1)
        self.label_q.setEnabled(1)
        self.label_split.setEnabled(1)
        self.label_inputformat.setEnabled(1)
        self.label_6.setEnabled(1)
        self.label_5.setEnabled(1)
        self.comboBox_colorspace.setEnabled(1)
        self.comboBox_inputFormat.setEnabled(1)
        self.comboBox_quality.setEnabled(1)
        self.presetbox.setEnabled(1)
        self.checkBox_hdr.setEnabled(1)
        self.checkBox_minsplit.setEnabled(1)
        self.checkBox_resume.setEnabled(1)
        if (self.spinBox_speed.value() < 7):
            self.checkBox_rtenc.setEnabled(1)
        self.checkBox_tempfolder.setEnabled(1)
        if (self.checkBox_audio.isChecked()):
            self.spinBox_audio.setEnabled(1)
            self.label_audio.setEnabled(1)
            self.audioqualitybox.setEnabled(1)
            self.label_audioquality.setEnabled(1)
        self.spinBox_quality.setEnabled(1)
        self.checkBox_bitrate.setEnabled(1)
        self.label_preset.setEnabled(1)
        if (not self.checkBox_bitrate.isChecked()):
            self.label_boost.setEnabled(1)
            self.comboBox_quality.setEnabled(1)
            self.label_quality.setEnabled(1)
        if (not self.checkBox_rtenc.isChecked()):
            self.checkBox_twopass.setEnabled(1)
        self.label_status.setEnabled(0) # self.setupUi(self)
        print("Enabled all buttons, returning program to normal")


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = window()
    window.show()
    sys.exit(app.exec_())
