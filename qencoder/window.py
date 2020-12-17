#!/usr/bin/python3
# This Python file uses the following encoding: utf-8
import glob
import shlex
import concurrent
import concurrent.futures

from PyQt5 import QtCore
from PyQt5.QtWidgets import QFileDialog, QMainWindow, QMessageBox
from functools import partial

import signal
import sys

from qencoder.mainwindow import Ui_qencoder
from parallelencode import Callbacks, run

import traceback

from pathlib import Path
import os
from time import sleep
import psutil
import multiprocessing

import pickle

canLoadScenedetect = 1

try:
    from scenedetect.video_manager import VideoManager
except ImportError as e:
    canLoadScenedetect = 0
    print("Error loading pyscenedetect. Either it is missing or not properly installed.")

hasLsmash = 1
try:
    from vapoursynth import core
    core.lsmas.get_functions()
except:
    hasLsmash = 0
    print("Error loading lsmash. Either vapoursynth is missing or lsmash is not installed.")

if sys.platform.startswith('win'):
    hasLsmash = 0
    print("Lsmash does not work properly on windows. Please switch to Linux or wait for qencoder 2.0 to properly release for a fix.")

# baseUIClass, baseUIWidget = uic.loadUiType("mainwindow.ui")


class window(QMainWindow, Ui_qencoder):
    twopassState = True
    realtimeState = False
    qualityState = 3
    audioState = 4
    runningEncode = False
    runningQueueMode = False
    currentFrames = 0
    totalFrames = 0
    encodeStage = 0
    encodeList = []
    currentFile = ""
    scenedetectFailState = -1
    currentlyRunning = 0
    killFlag = 0
    if 'APPDATA' in os.environ:
        confighome = os.environ['APPDATA']
    elif 'XDG_CONFIG_HOME' in os.environ:
        confighome = os.environ['XDG_CONFIG_HOME']
    else:
        confighome = os.path.join(os.environ['HOME'], '.config')
    configpath = os.path.join(confighome, 'qencoder.qec')

    def __init__(self, *args, **kwargs):
        global canLoadScenedetect
        global hasLsmash
        self.canLoadScenedetect = canLoadScenedetect
        self.hasLsmash = hasLsmash
        QMainWindow.__init__(self, *args, **kwargs)
        self.setupUi(self)
        self.inputFileChoose.clicked.connect(self.inputFileSelect)
        self.outputFileChoose.clicked.connect(self.outputFileSelect)
        self.pushButton_vmafmodel.clicked.connect(self.inputVmafSelect)
        self.label_audio.setEnabled(0)
        enable_slot = partial(self.audioEnableState, self.checkBox_audio)
        disable_slot = partial(self.audioDisableState, self.checkBox_audio)
        self.checkBox_audio.stateChanged.connect(lambda x: enable_slot() if x else disable_slot())

        enable_slot2 = partial(self.bitrateEnableState, self.checkBox_bitrate)
        disable_slot2 = partial(self.bitrateDisableState, self.checkBox_bitrate)
        self.checkBox_bitrate.stateChanged.connect(lambda x: enable_slot2() if x else disable_slot2())

        self.pushButton.clicked.connect(self.encodeVideo)
        self.pushButton_encQueue.clicked.connect(self.encodeVideoQueue)
        self.pushButton_encQueue.setEnabled(0)
        self.comboBox_quality.activated[int].connect(self.changeQPreset)
        self.presetbox.activated[int].connect(self.changePresetSimple)
        self.comboBox_colorspace.activated[int].connect(self.changeColorspace)
        self.comboBox_splitmode.activated[int].connect(self.changeSplitmode)

        self.comboBox_encoder.activated[int].connect(self.changeEncoder)

        self.spinBox_speed.valueChanged.connect(self.changePresetAdvanced)
        self.spinBox_quality.valueChanged.connect(self.customQPreset)
        self.checkBox_rtenc.stateChanged.connect(self.changeRTState)
        self.checkBox_videocmd.stateChanged.connect(self.customVidCmd)
        self.checkBox_audiocmd.stateChanged.connect(self.customAudCmd)
        self.checkBox_ffmpegcmd.stateChanged.connect(self.customFFCmd)
        self.actionOpen.triggered.connect(self.inputFileSelect)
        self.actionSave.triggered.connect(self.outputFileSelect)
        self.actionExit.triggered.connect(self.quitProgram)
        self.actionSave_Queue.triggered.connect(self.saveQueueAuto)
        self.actionSave_Queue_As.triggered.connect(self.saveQueueTo)
        self.actionOpen_Queue.triggered.connect(self.openQueueFrom)
        self.actionSave_Preset.triggered.connect(self.savePresetAs)
        self.actionOpen_Preset.triggered.connect(self.openPresetFrom)
        self.actionReset_All_Settings.triggered.connect(self.resetAllSettings)
        self.actionAdd_folder_to_queue.triggered.connect(self.addFolderToQueue)
        self.pushButton_save.setEnabled(0)
        self.pushButton_save.clicked.connect(self.saveToQueue)
        self.tabWidget.currentChanged[int].connect(self.setCustomText)
        self.pushButton_up.clicked.connect(self.queueMoveUp)
        self.pushButton_down.clicked.connect(self.queueMoveDown)
        self.pushButton_del.clicked.connect(self.removeFromQueue)
        self.pushButton_edit.clicked.connect(self.editCurrentQueue)
        self.checkBox_cropping.clicked.connect(self.enableCropping)
        self.checkBox_rescale.clicked.connect(self.enableRescale)
        self.checkBox_vmaf.clicked.connect(self.enableDisableVmaf)
        if (len(sys.argv) > 1):
            self.inputPath.setText(sys.argv[1])

        # this dictionary will be use to map combobox index into a values
        self.qualitydict = {
            0: 40,
            1: 36,
            2: 32,
            3: 28,
            4: 26,
            5: 24,
            6: 20,
            7: 10,
            8: 0
        }

        self.colorspacedict = {
            0: ["", "--color-space=unknown"],
            1: ["--color-primaries=bt709 --transfer-characteristics=bt709 --matrix-coefficients=bt709",
                "--color-space=bt709"],
            2: ["--color-primaries=bt601 --transfer-characteristics=bt601 --matrix-coefficients=bt601",
                "--color-space=bt601"],
            3: ["--color-primaries=bt2020 --transfer-characteristics=smpte2084 --matrix-coefficients=bt2020ncl",
                "--color-space=bt2020"],
        }

        try:
            filehandler = open(self.configpath, 'rb')
            settings = pickle.load(filehandler)
            self.setFromPresetDict(settings, False)
            self.enableCropping()
            self.enableRescale()
            self.enableDisableVmaf()
        except:
            print("Unable to load existing preset at: " + str(self.configpath) + ".")
            print("Possibly the first time you have run this, corrupted, or an older version")
            print("Do not report this")
            self.enableCropping()
            self.enableRescale()
            self.enableDisableVmaf()
        # self.speedButton.changeEvent.connect(self.setSpeed)
        self.checkBox_lsmash.setEnabled(hasLsmash)
        if canLoadScenedetect == 0:
            if self.comboBox_splitmode.currentIndex() == 2:
                self.comboBox_splitmode.setCurrentIndex(0)
            self.comboBox_splitmode.model().item(2).setEnabled(False)
        self.changeSplitmode(self.comboBox_splitmode.currentIndex(), False)

    def changeSplitmode(self, newPreset, setval=True):
        if newPreset == 0:
            self.doubleSpinBox_split.setEnabled(True)
            self.doubleSpinBox_split.setDecimals(3)
            if setval:
                self.doubleSpinBox_split.setValue(0.3)
            self.doubleSpinBox_split.setMaximum(1.0)
            self.doubleSpinBox_split.setMinimum(0.001)
            self.doubleSpinBox_split.setSingleStep(0.01)
            self.spinBox_maxkfdist.setMinimum(0)
        elif newPreset == 1:
            self.doubleSpinBox_split.setEnabled(False)
            self.spinBox_maxkfdist.setMinimum(2)
        else:
            self.doubleSpinBox_split.setEnabled(True)
            if setval:
                self.doubleSpinBox_split.setValue(35)
            self.doubleSpinBox_split.setMaximum(100)
            self.doubleSpinBox_split.setMinimum(1)
            self.doubleSpinBox_split.setSingleStep(1)
            self.doubleSpinBox_split.setDecimals(0)
            self.spinBox_maxkfdist.setMinimum(0)

    def enableDisableVmaf(self):
        state = self.checkBox_vmaf.isChecked()
        self.label_vmafpath.setEnabled(state)
        self.pushButton_vmafmodel.setEnabled(state)
        self.label_qmin.setEnabled(state)
        self.label_target.setEnabled(state)
        self.label_teststeps.setEnabled(state)
        self.spinBox_vmafsteps.setEnabled(state)
        self.spinBox_minq.setEnabled(state)
        self.doubleSpinBox_vmaf.setEnabled(state)
        self.spinBox_maxq.setEnabled(state)
        self.label_maxq.setEnabled(state)

    def enableRescale(self):
        state = self.checkBox_rescale.isChecked()
        self.spinBox_xres.setEnabled(state)
        self.spinBox_yres.setEnabled(state)
        self.label_xres.setEnabled(state)
        self.label_yres.setEnabled(state)

    def enableCropping(self):
        state = self.checkBox_cropping.isChecked()
        self.spinBox_croptop.setEnabled(state)
        self.spinBox_cropdown.setEnabled(state)
        self.spinBox_cropleft.setEnabled(state)
        self.spinBox_cropright.setEnabled(state)

    def addFolderToQueue(self):
        buttonReply = QMessageBox.question(self, 'Add folder to queue?',
                                           "The folder chosen will have all detected video files in it added to the queue using the current settings. Make sure your settings are correct before doing this. Continue?",
                                           QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if buttonReply != QMessageBox.Yes:
            return
        else:
            foldername = QFileDialog.getExistingDirectory(caption="Input Folder")
            newfoldername = QFileDialog.getExistingDirectory(caption="Output Folder")
            add_enc = False
            if foldername == newfoldername:
                add_enc = True
            types = ('*.mkv', '*.mp4', '*.webm', '*.y4m', '*.avi')
            files_grabbed = []
            for files in types:
                files_grabbed.extend(glob.glob(foldername + "/" + files))
            for fil in files_grabbed:
                self.inputPath.setText(fil)
                dirn, fname = os.path.split(fil)
                if add_enc:
                    fname = "enc_" + fname
                if not fname.endswith(".mkv") and not fname.endswith(".webm"):
                    fname = fname + ".mkv"
                self.outputPath.setText(os.path.join(dirn, fname))
                self.saveToQueue()
            self.inputPath.setText("")
            self.outputPath.setText("")
            self.pushButton.setEnabled(False)
            self.tabWidget.setCurrentIndex(5)

    def editCurrentQueue(self):
        if (self.listWidget.currentRow() <= -1):
            return
        buttonReply = QMessageBox.question(self, 'Overwrite existing encode settings?',
                                           "Clicking yes will move the queue item into your current encoding settings allowing you to edit it, but it will also override your existing encoding settings.",
                                           QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if buttonReply != QMessageBox.Yes:
            return
        else:
            self.setFromPresetDict(self.encodeList[self.listWidget.currentRow()][1], True)
            self.inputPath.setText(str(self.encodeList[self.listWidget.currentRow()][0]['input']))
            self.outputPath.setText(str(self.encodeList[self.listWidget.currentRow()][0]['output_file']))
            self.pushButton.setEnabled(1)
            self.pushButton_save.setEnabled(1)
            del self.encodeList[self.listWidget.currentRow()]
            self.redrawQueueList()
            self.enableCropping()
            self.enableRescale()
            self.enableDisableVmaf()

    def encodeFinished(self, taskname, errorCode):
        if (not self.runningQueueMode) or int(taskname) == -1:
            self.currentlyRunning = 0
            if errorCode == 0:
                self.pushButton.setEnabled(1)
                self.label_status.setText("Encoding complete!")
                self.progressBar_total.setValue(100)
                self.finalizeEncode()
            else:
                self.pushButton.setEnabled(1)
                self.pushButton.setStyleSheet("color: red; background-color: white")
                self.pushButton.setText("Reset")
                self.label_status.setText("ERR. See temp/log.log")
        else:
            taskNumber = int(taskname)
            q = self.getQueueIndexData(taskNumber)
            item = self.listWidget.item(taskNumber)
            if errorCode == 0:
                item.setText("Complete: " + q)
            else:
                item.setText("Failed: " + q)

    def addFrames(self, taskname, addFrames):
        if not self.runningQueueMode:
            self.currentFrames += addFrames
            self.progressBar_total.setValue(int(90 * self.currentFrames / self.totalFrames) + 10)
            self.label_status.setText("Encoding: " + str(self.currentFrames) + "/" + str(self.totalFrames))
        else:
            taskNumber = int(taskname)
            self.currentFrames[taskNumber] += addFrames
            q = self.getQueueIndexData(taskNumber)
            item = self.listWidget.item(taskNumber)
            item.setText("Encoding: " + str(self.currentFrames[taskNumber]) + "/" +
                         str(self.totalFrames[taskNumber]) + " progress: " +
                         str(int(90 * self.currentFrames[taskNumber] / self.totalFrames[taskNumber]) + 10) + "% " + q)

    def startEncode(self, taskname, totalFrames, initFrames):
        if not self.runningQueueMode:
            self.totalFrames = totalFrames
            self.currentFrames = initFrames
            self.progressBar_total.setValue(int(90 * initFrames / totalFrames) + 10)
            self.label_status.setText("Encoding: " + str(initFrames) + "/" + str(totalFrames))
        else:
            taskNumber = int(taskname)
            self.currentFrames[taskNumber] = initFrames
            self.totalFrames[taskNumber] = totalFrames
            q = self.getQueueIndexData(taskNumber)
            item = self.listWidget.item(taskNumber)
            item.setText("Encoding: " + str(initFrames) + "/" + str(totalFrames) + " progress: " + str(int(90 * initFrames / totalFrames) + 10) + "% " + q)
            self.label_status.setText("See queue for progress")

    def newTask(self, taskname, taskDesc: str, taskFrames: int):
        if not self.runningQueueMode:
            if taskDesc.startswith("Pyscene"):
                self.label_status.setText("Pyscenedetect... please wait")
                self.progressBar_total.setValue(5)
        else:
            if taskDesc.startswith("Pyscene"):
                taskNumber = int(taskname)
                q = self.getQueueIndexData(taskNumber)
                item = self.listWidget.item(taskNumber)
                item.setText("Pyscenedetect... please wait " + q)

    def resetAllSettings(self):
        buttonReply = QMessageBox.question(self, 'Factory reset all settings?',
                                           "Clicking yes will cause the program to close and reset all settings. You may lose any existing encodes.",
                                           QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if buttonReply != QMessageBox.Yes:
            return
        else:
            os.remove(Path(self.configpath))
            if not sys.platform.startswith('win'):
                os.killpg(0, signal.SIGTERM)
            sys.exit()

    def openPresetFrom(self):
        filename = QFileDialog.getOpenFileName(filter="Qencoder encoder config (*.qec)")
        newlist = []
        if (filename[0].endswith(".qec")):
            pass
        elif (len(filename[0]) > 0):
            self.outputPath.setText(filename[0] + ".qec")
        else:
            return
        filehandler = open(filename[0], 'rb')
        tempdict = pickle.load(filehandler)
        self.setFromPresetDict(tempdict, True)

    def savePresetAs(self):
        filename = QFileDialog.getSaveFileName(filter="Qencoder encoder config (*.qec)")
        if (filename[0].endswith(".qec")):
            pass
        elif (len(filename[0]) > 0):
            self.outputPath.setText(filename[0] + ".qec")
        else:
            return
        file_pi = open(filename[0], 'wb')
        pickle.dump(self.getPresetDict(), file_pi)

    def closeEvent(self, event):
        print("Writing current settings to config")
        curSettings = self.getPresetDict()
        file_pi = open(self.configpath, 'wb')
        pickle.dump(curSettings, file_pi)
        file_pi.close()
        if not sys.platform.startswith('win'):
            os.killpg(0, signal.SIGTERM)
        event.accept()

    def saveQueueAuto(self):
        if (len(self.currentFile) < 1):
            self.saveQueueTo()
        else:
            file_pi = open(self.currentFile, 'wb')
            pickle.dump(self.encodeList, file_pi)

    def saveQueueTo(self):
        filename = QFileDialog.getSaveFileName(filter="Qencoder encoder queue data (*.eqd)")
        if (filename[0].endswith(".eqd")):
            pass
        elif (len(filename[0]) > 0):
            self.outputPath.setText(filename[0] + ".eqd")
        else:
            return
        file_pi = open(filename[0], 'wb')
        pickle.dump(self.encodeList, file_pi)
        self.currentFile = filename[0]

    def openQueueFrom(self):
        filename = QFileDialog.getOpenFileName(filter="Qencoder encoder queue data (*.eqd)")
        newlist = []
        if (filename[0].endswith(".eqd")):
            pass
        elif (len(filename[0]) > 0):
            self.outputPath.setText(filename[0] + ".eqd")
        else:
            return
        filehandler = open(filename[0], 'rb')
        self.encodeList = pickle.load(filehandler)
        self.currentFile = filename[0]
        self.redrawQueueList()
        self.tabWidget.setCurrentIndex(5)

    def queueMoveUp(self):
        if (self.listWidget.currentRow() > 0):
            self.encodeList[self.listWidget.currentRow()], self.encodeList[self.listWidget.currentRow() - 1] = \
            self.encodeList[self.listWidget.currentRow() - 1], self.encodeList[self.listWidget.currentRow()]
            self.redrawQueueList()

    def queueMoveDown(self):
        if (self.listWidget.currentRow() < (self.listWidget.count() - 1)):
            self.encodeList[self.listWidget.currentRow()], self.encodeList[self.listWidget.currentRow() + 1] = \
            self.encodeList[self.listWidget.currentRow() + 1], self.encodeList[self.listWidget.currentRow()]
            self.redrawQueueList()

    def removeFromQueue(self):
        if (len(self.encodeList) > 0):
            index = self.listWidget.currentRow()
            del self.encodeList[index]
            self.redrawQueueList()

    def saveToQueue(self):
        self.encodeList.append([self.getArgs(), self.getPresetDict()])
        self.redrawQueueList()
        self.outputPath.setText("")
        self.pushButton.setEnabled(0)
        self.pushButton_encQueue.setEnabled(1)
        self.pushButton_save.setEnabled(0)

    def getQueueIndexData(self, index):
        q = self.encodeList[index]
        return str(q[0]['input'].parts[-1]) + " -> " + str(q[0]['output_file'].parts[-1])

    def redrawQueueList(self):
        self.listWidget.clear()
        for i in self.encodeList:
            inputFile = i[0]['input'].parts[-1]
            outputFile = i[0]['output_file'].parts[-1]
            finalString = inputFile + " -> " + outputFile
            if (i[1]['brmode']):
                finalString += ", " + str(i[1]['qual']) + "kbps"
            else:
                finalString += ", crf=" + str(i[1]['qual']) + ""
            if (i[1]['rtenc']):
                finalString += ", spd=" + str(i[1]['cpuused']) + "r"
            else:
                finalString += ", spd=" + str(i[1]['cpuused'])
            finalString += ", 2p=" + str(int(i[1]['2p']))
            if (i[1]['enc'] == 0):
                finalString += ", enc=av1"
            elif (i[1]['enc'] == 1):
                finalString += ", enc=vp9"
            else:
                finalString += ", enc=vp8"
            if (i[1]['audio']):
                finalString += ", aud=" + str(i[1]['audiobr']) + "k"
            self.listWidget.addItem(finalString)
        if (len(self.encodeList) > 0):
            self.pushButton_encQueue.setEnabled(1)
        else:
            self.pushButton_encQueue.setEnabled(0)

    def quitProgram(self):
        sys.exit(0)

    def customVidCmd(self, newState):
        self.textEdit_videocmd.setEnabled(newState)
        if (not newState):
            self.textEdit_videocmd.setPlainText(self.getVideoParams())

    def customFFCmd(self, newState):
        self.textEdit_ffmpegcmd.setEnabled(newState)
        if (not newState):
            self.textEdit_ffmpegcmd.setPlainText(self.getFFMPEGParams())

    def customAudCmd(self, newState):
        self.textEdit_audiocmd.setEnabled(newState)
        if (not newState):
            self.textEdit_audiocmd.setPlainText(self.getAudioParams())

    def setCustomText(self, i):
        self.textEdit_ffmpegcmd.setPlainText(self.getFFMPEGParams())
        self.textEdit_videocmd.setPlainText(self.getVideoParams())
        self.textEdit_audiocmd.setPlainText(self.getAudioParams())

    def getCPUUsed(self):
        if (self.presetbox.currentIndex() == 9):
            return self.spinBox_speed.value()
        if (self.comboBox_encoder.currentIndex() == 0):
            return (8 - self.presetbox.currentIndex())
        if (self.comboBox_encoder.currentIndex() == 1):
            return -int((self.presetbox.currentIndex() - 4) * 2.25)  # Maps the presets between -9 and 9
        if (self.comboBox_encoder.currentIndex() == 2):
            return -int((self.presetbox.currentIndex() - 4) * 4.125)  # Maps the presets between -16 and 16
        return 0

    def getColorData(self):
        # Get indexes of current colorspace comboBox
        inputSpace = self.comboBox_colorspace.currentIndex()
        # if colorspace index is 5 uses a custom value set by the user
        if (inputSpace == 4):
            return self.lineEdit_colordata.text()
        # return empty string if current encoder combobox indexes is 2
        if (self.comboBox_encoder.currentIndex() == 2):
            return ""
        # else map the colorspace index into a list of av1,vp9 color space then return the appropriate string based on the encoder
        else:
            return self.colorspacedict[inputSpace][self.comboBox_encoder.currentIndex()]

    def changeEncoder(self, newencoder):
        spdpreset = self.presetbox.currentIndex()
        if (newencoder == 0):
            self.spinBox_speed.setMaximum(8)
            self.spinBox_speed.setMinimum(0)
        elif (newencoder == 1):
            self.spinBox_speed.setMaximum(9)
            self.spinBox_speed.setMinimum(-9)
        else:
            self.spinBox_speed.setMaximum(16)
            self.spinBox_speed.setMinimum(-16)
        self.spinBox_speed.setValue(self.getCPUUsed())
        self.lineEdit_colordata.setText(self.getColorData())
        self.presetbox.setCurrentIndex(spdpreset)
        self.changePresetSimple(spdpreset)
        if (newencoder > 1):
            self.comboBox_colorspace.setCurrentIndex(0)
            self.comboBox_colorspace.setEnabled(0)
            self.lineEdit_colordata.setEnabled(0)
            self.label_2.setEnabled(0)
        else:
            self.comboBox_colorspace.setEnabled(1)
            if (self.comboBox_colorspace.currentIndex() == 4):
                self.lineEdit_colordata.setEnabled(1)
            self.label_2.setEnabled(1)

    def changeColorspace(self, newspace):
        colorInfo = self.getColorData()
        self.lineEdit_colordata.setText(colorInfo)
        if (newspace == 4):
            self.lineEdit_colordata.setEnabled(1)
        else:
            self.lineEdit_colordata.setEnabled(0)

    def changeRTState(self, newState):
        if (newState):
            if (self.checkBox_twopass.isEnabled()):
                self.twopassState = self.checkBox_twopass.isChecked()
            self.checkBox_twopass.setChecked(0)
            self.checkBox_twopass.setEnabled(0)
        else:
            self.checkBox_twopass.setChecked(self.twopassState)
            self.checkBox_twopass.setEnabled(1)

    def customQPreset(self):
        self.comboBox_quality.setCurrentIndex(9)  # custom

    def changeQPreset(self, i):
        trueQuality = self.getQuality(i)
        self.spinBox_quality.setValue(trueQuality)
        self.qualityState = i
        self.comboBox_quality.setCurrentIndex(i)

    def changePresetAdvanced(self):
        if (self.spinBox_speed.value() > 6 and self.comboBox_encoder.currentIndex() == 0):
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
        self.presetbox.setCurrentIndex(9)

    def changePresetSimple(self, i):
        if (i <= 1 and self.comboBox_encoder.currentIndex() == 0):
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
        self.spinBox_speed.setValue(self.getCPUUsed())
        self.presetbox.setCurrentIndex(i)


    def getQuality(self, qval):
        if (qval < 9):
            return self.qualitydict[qval]
        else:
            return self.spinBox_quality.value()

    def inputVmafSelect(self):
        filename = QFileDialog.getOpenFileName(filter="VMAF models(*.pkl *.model);;All(*)")
        self.label_vmafpath.setText(filename[0])

    def inputFileSelect(self):
        filename = QFileDialog.getOpenFileName(
            filter="Videos(*.mp4 *.mkv *.webm *.flv *.gif *.3gp *.wmv *.avi *.y4m);;All(*)")
        self.inputPath.setText(filename[0])
        if (len(self.outputPath.text()) > 1):
            self.pushButton.setEnabled(1)
            self.pushButton_save.setEnabled(1)

    def outputFileSelect(self):
        filename = QFileDialog.getSaveFileName(filter="mkv and webm videos(*.mkv *.webm)")
        if (filename[0].endswith(".mkv") or filename[0].endswith(".webm")):
            self.outputPath.setText(filename[0])
        elif (len(filename[0]) > 0):
            self.outputPath.setText(filename[0] + ".mkv")
        if (len(self.inputPath.text()) > 1):
            self.pushButton.setEnabled(1)
            self.pushButton_save.setEnabled(1)

    def audioEnableState(self, checkbox):
        self.label_audio.setEnabled(1)
        self.spinBox_audio.setReadOnly(0)
        self.spinBox_audio.setEnabled(1)

    def audioDisableState(self, checkbox):
        self.label_audio.setEnabled(0)
        self.spinBox_audio.setReadOnly(1)
        self.spinBox_audio.setEnabled(0)

    def bitrateEnableState(self, checkbox):
        self.label_q.setText("Bitrate (kbps)")
        self.checkBox_vmaf.setChecked(0)
        self.checkBox_vmaf.setEnabled(0)
        self.spinBox_quality.setMaximum(99999)
        self.spinBox_quality.setMinimum(8)
        self.spinBox_quality.setValue(3000)
        self.comboBox_quality.setCurrentIndex(9)  # custom
        self.comboBox_quality.setEnabled(0)
        self.label_quality.setEnabled(0)

    def bitrateDisableState(self, checkbox):
        self.label_q.setText("CRF")
        self.checkBox_vmaf.setEnabled(1)
        self.spinBox_quality.setMaximum(63)
        self.spinBox_quality.setMinimum(0)
        self.spinBox_quality.setValue(30)
        self.comboBox_quality.setEnabled(1)
        self.label_quality.setEnabled(1)

    def getFFMPEGParams(self):
        if (self.checkBox_ffmpegcmd.isChecked()):
            return self.textEdit_ffmpegcmd.toPlainText()
        astr = ""
        addedStuff = False
        if (self.checkBox_cropping.isChecked() and (
                self.spinBox_cropdown.value() > 0 or self.spinBox_cropright.value() > 0 or self.spinBox_croptop.value() > 0 or self.spinBox_cropleft.value() > 0)):
            widthSub = self.spinBox_cropright.value() + self.spinBox_cropleft.value()
            heightSub = self.spinBox_croptop.value() + self.spinBox_cropdown.value()
            astr += "-filter:v \"crop=iw-" + str(widthSub) + ":ih-" + str(heightSub) + ":" + str(
                self.spinBox_cropleft.value()) + ":" + str(self.spinBox_croptop.value())
            addedStuff = True
        if (self.checkBox_rescale.isChecked()):
            if (addedStuff):
                astr += ",scale=" + str(self.spinBox_xres.value()) + ":" + str(self.spinBox_yres.value())
            else:
                astr += "-filter:v \"scale=" + str(self.spinBox_xres.value()) + ":" + str(self.spinBox_yres.value())
                addedStuff = True
        if (addedStuff):
            astr += "\""
        return astr

    def getVideoParams(self):
        if (self.checkBox_videocmd.isChecked()):
            return self.textEdit_videocmd.toPlainText()
        vparams = "--threads=" + str(self.spinBox_threads.value())
        if (self.spinBox_maxkfdist.value() > 0 and self.comboBox_splitmode.currentIndex() != 1):
            vparams += " --kf-max-dist=" + str(self.spinBox_maxkfdist.value())
        if (self.comboBox_encoder.currentIndex() < 2):
            vparams += " --tile-columns=1 --tile-rows=0 --cpu-used=" + str(self.spinBox_speed.value())
        else:
            vparams += " --codec=vp8 --cpu-used=" + str(self.spinBox_speed.value())

        if (self.comboBox_encoder.currentIndex() == 1):
            vparams += " --codec=vp9"

        if (self.checkBox_rtenc.isChecked()):
            vparams += " --rt"
        else:
            vparams += " --good"
        if (self.checkBox_bitrate.isChecked()):
            vparams += " --end-usage=vbr --target-bitrate=" + str(self.spinBox_quality.value())
        else:
            if (self.spinBox_quality.value() < 4 and self.comboBox_encoder.currentIndex() == 2):
                vparams += " --end-usage=q --cq-level=4"
            else:
                vparams += " --end-usage=q --cq-level=" + str(self.spinBox_quality.value())
            if (self.spinBox_quality.value() == 0 and self.comboBox_encoder.currentIndex() <= 1):
                vparams += " --lossless=1"

        if (self.checkBox_hdr.isChecked()):
            vparams += " --bit-depth=10 "
        else:
            vparams += " --bit-depth=8 "
        vparams += self.lineEdit_colordata.text()
        if (self.comboBox_inputFormat.currentIndex() <= 2):
            vparams += " --i420"
        elif (self.comboBox_inputFormat.currentIndex() <= 5):
            vparams += " --i422"
        else:
            vparams += " --i444"
        return vparams

    def getSplitMethod(self):
        if (self.comboBox_splitmode.currentIndex() == 0):
            return "ffmpeg"
        elif (self.comboBox_splitmode.currentIndex() == 1):
            return "time"
        else:
            return "pyscene"

    def getAudioParams(self):
        if (self.checkBox_audiocmd.isChecked()):
            return self.textEdit_audiocmd.toPlainText()
        if (self.checkBox_audio.isChecked()):
            return "-b:a " + str(self.spinBox_audio.value()) + "k -c:a libopus"
        else:
            return "-c:a copy"

    def getVmafFilter(self):
        astr = ""
        addedStuff = False
        if (self.checkBox_cropping.isChecked() and (
                self.spinBox_cropdown.value() > 0 or self.spinBox_cropright.value() > 0 or self.spinBox_croptop.value() > 0 or self.spinBox_cropleft.value() > 0)):
            widthSub = self.spinBox_cropright.value() + self.spinBox_cropleft.value()
            heightSub = self.spinBox_croptop.value() + self.spinBox_cropdown.value()
            astr += "crop=iw-" + str(widthSub) + ":ih-" + str(heightSub) + ":" + str(
                self.spinBox_cropleft.value()) + ":" + str(self.spinBox_croptop.value())
            addedStuff = True
        if self.checkBox_rescale.isChecked():
            if addedStuff:
                astr += ",scale=" + str(self.spinBox_xres.value()) + ":" + str(self.spinBox_yres.value())
            else:
                astr += "scale=" + str(self.spinBox_xres.value()) + ":" + str(self.spinBox_yres.value())
        return astr

    def getVmafRes(self):
        if self.checkBox_rescale.isChecked():
            return str(self.spinBox_xres.value()) + "x" + str(self.spinBox_yres.value())
        else:
            return "1920x1080"

    def setFromPresetDict(self, dict, restoreCropping):
        # 1.1 variables
        self.comboBox_encoder.setCurrentIndex(dict['enc'])
        self.changeEncoder(dict['enc'])
        self.doubleSpinBox_split.setValue(dict['splittr'])
        self.spinBox_speed.setValue(dict['cpuused'])
        self.spinBox_jobs.setValue(dict['jobs'])
        self.spinBox_audio.setValue(dict['audiobr'])
        self.spinBox_threads.setValue(dict['threads'])
        self.checkBox_audio.setChecked(dict['audio'])
        self.spinBox_quality.setValue(dict['qual'])
        self.checkBox_videocmd.setChecked(dict['cusvid'])
        self.checkBox_audiocmd.setChecked(dict['cusaud'])
        self.checkBox_ffmpegcmd.setChecked(dict['cusffmpeg'])
        self.textEdit_videocmd.setPlainText(dict['vidcmd'])
        self.textEdit_audiocmd.setPlainText(dict['audcmd'])
        self.textEdit_ffmpegcmd.setPlainText(dict['ffmpegcmd'])
        self.presetbox.setCurrentIndex(dict['preset'])
        self.comboBox_quality.setCurrentIndex(dict['vq'])
        self.checkBox_bitrate.setChecked(dict['brmode'])
        self.checkBox_hdr.setChecked(dict['10b'])
        self.checkBox_resume.setChecked(dict['resume'])
        self.checkBox_tempfolder.setChecked(dict['keeptmp'])
        self.checkBox_rtenc.setChecked(dict['rtenc'])
        self.twopassState = dict['2p']
        self.realtimeState = dict['rtenc']
        self.checkBox_twopass.setChecked(dict['2p'])
        if (self.twopassState and self.realtimeState):
            self.twopassState = True
            self.realtimeState = False
            self.checkBox_rtenc.setChecked(False)
            self.checkBox_twopass.setChecked(True)
            print("Resetting invalid twopass and realtime state combos")

        # 1.2 variables
        self.spinBox_maxkfdist.setValue(dict['maxkfdist'])

        # 1.5 variables
        self.comboBox_inputFormat.setCurrentIndex(dict['inputFmt'])
        self.comboBox_colorspace.setCurrentIndex(dict['colordataCS'])
        self.lineEdit_colordata.setText(dict['colordataText'])
        self.checkBox_vmaf.setChecked(dict['isTargetVMAF'])
        self.spinBox_minq.setValue(dict['TargetVMAFMinQ'])
        self.spinBox_maxq.setValue(dict['TargetVMAFMaxQ'])
        self.spinBox_vmafsteps.setValue(dict['TargetVMAFSteps'])
        self.doubleSpinBox_vmaf.setValue(dict['TargetVMAFValue'])
        self.label_vmafpath.setText(dict['TargetVMAFPath'])
        self.checkBox_shutdown.setChecked(dict['ShutdownAfter'])

        # 2.0 variables
        self.checkBox_lsmash.setChecked(dict['usinglsmas'])
        self.comboBox_splitmode.setCurrentIndex(dict['splitmethod'])
        self.spinBox_qjobs.setValue(dict['qjobs'])
        if (restoreCropping):
            self.checkBox_cropping.setChecked(dict["iscropping"])
            self.checkBox_rescale.setChecked(dict["rescale"])
            self.spinBox_xres.setValue(dict["rescalex"])
            self.spinBox_yres.setValue(dict["rescaley"])
            self.spinBox_croptop.setValue(dict["croptop"])
            self.spinBox_cropdown.setValue(dict["cropdown"])
            self.spinBox_cropright.setValue(dict["cropright"])
            self.spinBox_cropleft.setValue(dict["cropleft"])

    def getPresetDict(self):
        return {'2p': self.checkBox_twopass.isChecked(), 'audio': self.checkBox_audio.isChecked(),
                'enc': self.comboBox_encoder.currentIndex(),
                'preset': self.presetbox.currentIndex(),
                'vq': self.comboBox_quality.currentIndex(), 'brmode': self.checkBox_bitrate.isChecked(),
                '10b': self.checkBox_hdr.isChecked(), 'resume': self.checkBox_resume.isChecked(),
                'keeptmp': self.checkBox_tempfolder.isChecked(), 'rtenc': self.checkBox_rtenc.isChecked(),
                'qual': self.spinBox_quality.value(),
                'splittr': self.doubleSpinBox_split.value(), 'cpuused': self.spinBox_speed.value(),
                'jobs': self.spinBox_jobs.value(), 'audiobr': self.spinBox_audio.value(),
                'threads': self.spinBox_threads.value(),
                'cusvid': self.checkBox_videocmd.isChecked(), 'cusaud': self.checkBox_audiocmd.isChecked(),
                'cusffmpeg': self.checkBox_ffmpegcmd.isChecked(), 'vidcmd': self.textEdit_videocmd.toPlainText(),
                'audcmd': self.textEdit_audiocmd.toPlainText(), 'ffmpegcmd': self.textEdit_ffmpegcmd.toPlainText(),
                'maxkfdist': self.spinBox_maxkfdist.value(),
                'inputFmt': self.comboBox_inputFormat.currentIndex(),
                'colordataCS': self.comboBox_colorspace.currentIndex(),
                'colordataText': self.lineEdit_colordata.text(), 'isTargetVMAF': self.checkBox_vmaf.isChecked(),
                'TargetVMAFMinQ': self.spinBox_minq.value(), 'TargetVMAFMaxQ': self.spinBox_maxq.value(),
                'TargetVMAFSteps': self.spinBox_vmafsteps.value(), 'TargetVMAFValue': self.doubleSpinBox_vmaf.value(),
                'TargetVMAFPath': self.label_vmafpath.text(), 'ShutdownAfter': self.checkBox_shutdown.isChecked(),
                'usinglsmas' : self.checkBox_lsmash.isChecked(), 'splitmethod': self.comboBox_splitmode.currentIndex(),
                'qjobs' : self.spinBox_qjobs.value(), 'iscropping' : self.checkBox_cropping.isChecked(),
                'croptop' : self.spinBox_croptop.value(), 'cropright' : self.spinBox_cropright.value(),
                'cropleft' : self.spinBox_cropleft.value(), 'cropdown' : self.spinBox_cropdown.value(),
                'rescale' : self.checkBox_rescale.isChecked(), 'rescalex' : self.spinBox_xres.value(),
                'rescaley' : self.spinBox_yres.value()
                }

    def getArgs(self):
        args = {'video_params': shlex.split(self.getVideoParams()), 'input': Path(self.inputPath.text()), 'encoder': 'aom',
                'workers': self.spinBox_jobs.value(), 'audio_params': shlex.split(self.getAudioParams()),
                'threshold': self.doubleSpinBox_split.value(),
                'passes': (2 if self.checkBox_twopass.isChecked() else 1), 'output_file': Path(self.outputPath.text()),
                'scenes': None, 'resume': self.checkBox_resume.isChecked(),
                'keep': self.checkBox_tempfolder.isChecked(),
                'pix_format': self.comboBox_inputFormat.currentText(), 'ffmpeg': shlex.split(self.getFFMPEGParams()),
                'threads': self.spinBox_threads.value(),
                'split_method': self.getSplitMethod(),
                'chunk_method': ("vs_lsmash" if self.checkBox_lsmash.isChecked() and self.checkBox_lsmash.isEnabled() else "segment"),
                'temp': Path(
                str(os.path.dirname(self.outputPath.text())) + "/temp_" + str(
                    os.path.basename(self.outputPath.text()))), 'vmaf_steps': self.spinBox_vmafsteps.value(),
                'min_q': self.spinBox_minq.value(), 'max_q': self.spinBox_maxq.value(),
                'vmaf_target': (self.doubleSpinBox_vmaf.value() if self.checkBox_vmaf.isChecked() else None),
                'vmaf_path': self.label_vmafpath.text(), 'vmaf_filter': self.getVmafFilter(),
                'vmaf_res': self.getVmafRes(), 'time_split_interval': self.spinBox_maxkfdist.value()}

        if self.comboBox_encoder.currentIndex() >= 1:
            args['encoder'] = 'vpx'
        args['temp'] = Path(str((args['temp'])).replace("'", "_"))
        return args

    def encodeVideoQueue(self):
        if (self.runningEncode):
            self.encodeVideo1()
            return
        self.encodeVideo1()
        self.runningEncode = True
        self.runningQueueMode = True
        self.currentFrames = [0] * len(self.encodeList)
        self.totalFrames = [0] * len(self.encodeList)
        self.worker = EncodeWorker(self.encodeList, self, self.checkBox_shutdown.isChecked(), self.spinBox_qjobs.value())
        self.workerThread = QtCore.QThread()
        self.worker.newFrames.connect(self.addFrames)
        self.worker.startEncode.connect(self.startEncode)
        self.worker.newTask.connect(self.newTask)
        self.worker.encodeFinished.connect(self.encodeFinished)
        self.worker.moveToThread(self.workerThread)  # Move the Worker object to the Thread object
        self.workerThread.started.connect(self.worker.run)  # Init worker run() at startup (optional)
        self.workerThread.start()

    def encodeVideo(self):
        if (self.runningEncode):
            self.encodeVideo1()
            return
        args = [self.getArgs(), self.getPresetDict()]
        self.encodeVideo1()
        print("Running in non-queued mode with a single video")
        self.runningEncode = True
        self.runningQueueMode = False
        self.worker = EncodeWorker([args], self, self.checkBox_shutdown.isChecked(), 1)
        self.workerThread = QtCore.QThread()
        self.worker.newFrames.connect(self.addFrames)
        self.worker.startEncode.connect(self.startEncode)
        self.worker.newTask.connect(self.newTask)
        self.worker.encodeFinished.connect(self.encodeFinished)
        self.worker.moveToThread(self.workerThread)  # Move the Worker object to the Thread object
        self.workerThread.started.connect(self.worker.run)  # Init worker run() at startup (optional)
        self.workerThread.start()

    def encodeVideo1(self):
        if (self.runningEncode):
            if (self.currentlyRunning):
                buttonReply = QMessageBox.question(self, 'Stop encode?',
                                                   "Warning: You may lose encoding progress.",
                                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if buttonReply != QMessageBox.Yes:
                    return

            self.finalizeEncode()
            return
        print("Writing current settings to config")
        curSettings = self.getPresetDict()
        file_pi = open(self.configpath, 'wb')
        pickle.dump(curSettings, file_pi)
        file_pi.close()
        self.actionOpen.setEnabled(0)
        self.actionSave.setEnabled(0)
        self.actionSave_Queue.setEnabled(0)
        self.actionSave_Queue_As.setEnabled(0)
        self.actionOpen_Queue.setEnabled(0)
        self.actionSave_Preset.setEnabled(0)
        self.actionOpen_Preset.setEnabled(0)
        self.actionReset_All_Settings.setEnabled(0)
        self.label_3.setEnabled(0)
        self.label_threads.setEnabled(0)
        self.spinBox_threads.setEnabled(0)
        self.checkBox_videocmd.setEnabled(0)
        self.checkBox_audiocmd.setEnabled(0)
        self.checkBox_ffmpegcmd.setEnabled(0)
        self.textEdit_videocmd.setEnabled(0)
        self.textEdit_audiocmd.setEnabled(0)
        self.textEdit_ffmpegcmd.setEnabled(0)
        self.currentlyRunning = True
        self.pushButton.setEnabled(1)
        self.pushButton.setText("Cancel")
        self.pushButton_encQueue.setEnabled(0)
        self.pushButton_save.setEnabled(0)
        self.progressBar_total.setEnabled(1)
        self.spinBox_audio.setEnabled(0)
        self.spinBox_quality.setEnabled(0)
        self.spinBox_speed.setEnabled(0)
        self.doubleSpinBox_split.setEnabled(0)
        self.spinBox_jobs.setEnabled(0)
        self.label_jobs.setEnabled(0)
        self.inputFileChoose.setEnabled(0)
        self.outputFileChoose.setEnabled(0)
        self.label_2.setEnabled(0)
        self.label_audio.setEnabled(0)
        self.label_q.setEnabled(0)
        self.label_split.setEnabled(0)
        self.label_inputformat.setEnabled(0)
        self.label_6.setEnabled(0)
        self.comboBox_colorspace.setEnabled(0)
        self.comboBox_inputFormat.setEnabled(0)
        self.comboBox_quality.setEnabled(0)
        self.presetbox.setEnabled(0)
        self.checkBox_audio.setEnabled(0)
        self.checkBox_bitrate.setEnabled(0)
        self.checkBox_hdr.setEnabled(0)
        self.checkBox_resume.setEnabled(0)
        self.checkBox_rtenc.setEnabled(0)
        self.checkBox_tempfolder.setEnabled(0)
        self.checkBox_twopass.setEnabled(0)
        self.label_preset.setEnabled(0)
        self.label_quality.setEnabled(0)
        self.label_4.setEnabled(0)
        self.comboBox_encoder.setEnabled(0)
        self.pushButton_up.setEnabled(0)
        self.pushButton_down.setEnabled(0)
        self.pushButton_del.setEnabled(0)
        self.label_status.setEnabled(1)  # self.setupUi(self)
        self.label_status.setText("Initializing...")
        self.inputPath.setText("")
        self.outputPath.setText("")
        self.pushButton_del.setEnabled(0)
        self.listWidget.setEnabled(0)
        self.label_maxkfdist.setEnabled(0)
        self.spinBox_maxkfdist.setEnabled(0)
        self.pushButton_edit.setEnabled(0)
        self.checkBox_cropping.setEnabled(0)
        self.checkBox_rescale.setEnabled(0)
        self.label_xres.setEnabled(0)
        self.label_yres.setEnabled(0)
        self.spinBox_yres.setEnabled(0)
        self.spinBox_xres.setEnabled(0)
        self.spinBox_cropleft.setEnabled(0)
        self.spinBox_cropright.setEnabled(0)
        self.spinBox_croptop.setEnabled(0)
        self.spinBox_cropdown.setEnabled(0)
        self.checkBox_vmaf.setEnabled(0)
        self.label_qmin.setEnabled(0)
        self.label_teststeps.setEnabled(0)
        self.label_target.setEnabled(0)
        self.pushButton_vmafmodel.setEnabled(0)
        self.label_vmafpath.setEnabled(0)
        self.spinBox_minq.setEnabled(0)
        self.spinBox_vmafsteps.setEnabled(0)
        self.doubleSpinBox_vmaf.setEnabled(0)
        self.spinBox_maxq.setEnabled(0)
        self.label_maxq.setEnabled(0)
        self.checkBox_shutdown.setEnabled(0)
        self.checkBox_lsmash.setEnabled(0)
        self.comboBox_splitmode.setEnabled(0)
        self.label_splitmode.setEnabled(0)
        self.label_qjobs.setEnabled(0)
        self.spinBox_qjobs.setEnabled(0)

    def finalizeEncode(self):
        self.workerThread.quit()
        self.workerThread.wait(2000)
        self.killFlag = True
        self.workerThread.wait()
        self.killFlag = False
        self.runningEncode = False
        self.currentlyRunning = False
        self.pushButton.setStyleSheet("")
        self.pushButton.setText("▶  Encode")
        self.label_threads.setEnabled(1)
        self.spinBox_threads.setEnabled(1)
        self.checkBox_audio.setEnabled(1)
        self.spinBox_speed.setEnabled(1)
        self.spinBox_speed.setValue(self.spinBox_speed.value())
        self.spinBox_jobs.setEnabled(1)
        self.label_jobs.setEnabled(1)
        self.inputFileChoose.setEnabled(1)
        self.outputFileChoose.setEnabled(1)
        self.inputPath.setText("")
        self.outputPath.setText("")
        self.label_threads.setEnabled(1)
        self.spinBox_threads.setEnabled(1)
        self.label_2.setEnabled(1)
        self.label_q.setEnabled(1)
        self.checkBox_shutdown.setEnabled(1)
        self.label_split.setEnabled(1)
        self.comboBox_splitmode.setEnabled(1)
        self.label_splitmode.setEnabled(1)
        if self.comboBox_splitmode.currentIndex() != 1:
            self.doubleSpinBox_split.setEnabled(1)

        self.label_inputformat.setEnabled(1)
        self.label_6.setEnabled(1)
        self.label_5.setEnabled(1)
        self.comboBox_colorspace.setEnabled(1)
        self.comboBox_inputFormat.setEnabled(1)
        self.comboBox_quality.setEnabled(1)
        self.presetbox.setEnabled(1)
        self.checkBox_hdr.setEnabled(1)
        self.checkBox_resume.setEnabled(1)
        if (self.spinBox_speed.value() < 7 or self.comboBox_encoder.currentIndex() != 0):
            self.checkBox_rtenc.setEnabled(1)
        self.checkBox_tempfolder.setEnabled(1)
        if (self.checkBox_audio.isChecked()):
            self.spinBox_audio.setEnabled(1)
            self.label_audio.setEnabled(1)
        self.spinBox_quality.setEnabled(1)
        self.checkBox_bitrate.setEnabled(1)
        self.label_preset.setEnabled(1)
        self.enableDisableVmaf()
        if (not self.checkBox_bitrate.isChecked()):
            self.checkBox_vmaf.setEnabled(1)
            self.comboBox_quality.setEnabled(1)
            self.label_quality.setEnabled(1)
        if (not self.checkBox_rtenc.isChecked()):
            self.checkBox_twopass.setEnabled(1)
        self.label_status.setEnabled(0)  # self.setupUi(self)
        self.label_4.setEnabled(1)
        self.comboBox_encoder.setEnabled(1)
        self.label_3.setEnabled(1)
        self.checkBox_videocmd.setEnabled(1)
        self.checkBox_audiocmd.setEnabled(1)
        self.checkBox_ffmpegcmd.setEnabled(1)
        if (self.checkBox_videocmd.isChecked()):
            self.textEdit_videocmd.setEnabled(1)
        if (self.checkBox_ffmpegcmd.isChecked()):
            self.textEdit_ffmpegcmd.setEnabled(1)
        if (self.checkBox_audiocmd.isChecked()):
            self.textEdit_audiocmd.setEnabled(1)
        self.encodeList = []
        self.redrawQueueList()
        self.pushButton_up.setEnabled(1)
        self.pushButton_down.setEnabled(1)
        self.pushButton_del.setEnabled(1)
        self.pushButton_edit.setEnabled(1)
        self.listWidget.setEnabled(1)
        self.pushButton_save.setEnabled(0)
        self.progressBar_total.setValue(0)
        self.pushButton.setEnabled(0)
        self.pushButton_encQueue.setEnabled(0)
        self.label_maxkfdist.setEnabled(1)
        self.spinBox_maxkfdist.setEnabled(1)
        self.actionOpen.setEnabled(1)
        self.actionSave.setEnabled(1)
        self.actionSave_Queue.setEnabled(1)
        self.actionSave_Queue_As.setEnabled(1)
        self.actionOpen_Queue.setEnabled(1)
        self.actionSave_Preset.setEnabled(1)
        self.actionOpen_Preset.setEnabled(1)
        self.actionReset_All_Settings.setEnabled(1)
        self.checkBox_cropping.setEnabled(1)
        self.checkBox_rescale.setEnabled(1)
        self.label_qjobs.setEnabled(1)
        self.spinBox_qjobs.setEnabled(1)
        self.checkBox_lsmash.setEnabled(self.hasLsmash)
        self.enableCropping()
        self.enableRescale()
        self.enableDisableVmaf()
        print("Enabled all buttons, returning program to normal")


class EncodeWorker(QtCore.QObject):
    newTask = QtCore.pyqtSignal(str, str, int)
    startEncode = QtCore.pyqtSignal(str, int, int)
    encodeFinished = QtCore.pyqtSignal(str, bool)
    newFrames = QtCore.pyqtSignal(str, int)
    runningPav1n = False

    def __init__(self, argdata, window, shutdown, numcores):
        super().__init__()
        self.argdat = argdata
        self.window = window
        self.shutdown = shutdown
        self.numcores = numcores
        self.istty = sys.stdin.isatty()

    def runProcessing(self, dictargs, index):
        if self.window.killFlag:
            return
        self.window.scenedetectFailState = -1
        c = Callbacks()
        c.subscribe("newtask", self.newTask.emit, str(index))
        c.subscribe("startencode", self.startEncode.emit, str(index))
        c.subscribe("newframes", self.newFrames.emit, str(index))
        c.subscribe("terminate", self.encodeFinished.emit, str(index))

        t = multiprocessing.Process(target=run, args=(dictargs, c))
        t.start()
        while t.is_alive():
            sleep(0.05)
            if self.window.killFlag:
                print("Killing all children processes. Hopefully this works.")
                parent = psutil.Process(os.getpid())
                for child in parent.children(recursive=True):  # or parent.children() for recursive=False
                    child.kill()
                t.join()
                return
        print("\n\nEncode completed for " + str(dictargs['input']) + " -> " + str(dictargs['output_file']))

    def run(self):
        print("Running")
        self.runningPav1n = True
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.numcores) as executor:
            future_cmd = {executor.submit(self.runProcessing, self.argdat[i][0], i): i for i in range(len(self.argdat))}
            for future in concurrent.futures.as_completed(future_cmd):
                try:
                    future.result()
                except Exception as e:
                    print(e)
                    traceback.print_exc()
        if len(self.argdat) > 1:
            self.encodeFinished.emit("-1", 0)
        if self.shutdown:
            if sys.platform.startswith('win'):
                os.system('shutdown -s')
            else:
                try:
                    os.system('systemctl poweroff')
                except Exception as e:
                    # If that doesn't work we can try shutting down the "other" way
                    os.system("shutdown now -h")

