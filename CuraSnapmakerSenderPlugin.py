# Copyright (c) 2017 Ultimaker B.V.
# This example is released under the terms of the AGPLv3 or higher.

from asyncio.log import logger
from asyncio.windows_events import NULL
from distutils.log import Log
import imp
import os.path #To get a file name to write to.
import socket
from typing import Dict, Type, TYPE_CHECKING, List, Optional, cast
import json
import threading
from collections import namedtuple
from io import BytesIO, StringIO
import typing
from . import SnapmakerGCodeWriter

from UM.Application import Application #To find the scene to get the current g-code to write.
from UM.FileHandler.WriteFileJob import WriteFileJob #To serialise nodes to text.
from UM.Logger import Logger
from UM.OutputDevice.OutputDevice import OutputDevice #An interface to implement.
from UM.OutputDevice.OutputDeviceError import WriteRequestFailedError,PermissionDeniedError #For when something goes wrong.
from UM.OutputDevice.OutputDevicePlugin import OutputDevicePlugin #The class we need to extend.
from UM.PluginRegistry import PluginRegistry
from UM.Extension import Extension
from UM.i18n import i18nCatalog
from UM.Mesh.MeshWriter import MeshWriter
from UM.Message import Message
from requests.sessions import to_native_string
from UM.Qt.ListModel import ListModel
import UM.PluginError

from cura.CuraApplication import CuraApplication
from PyQt6.QtCore import QModelIndex,QByteArray,QObject, QThread, QTimer, pyqtProperty, pyqtSignal, pyqtSlot,Qt,QAbstractTableModel,QVariant
from PyQt6.QtNetwork import QHttpMultiPart, QHttpPart, QNetworkRequest, QNetworkAccessManager
from PyQt6.QtNetwork import QNetworkReply
from PyQt6.QtQuick import QQuickWindow
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtQml import qmlRegisterType,QQmlListProperty

from . import SnapmakerApiV1

i18n_catalog = i18nCatalog("cura")

machinePrototype = namedtuple('Machine',['name','address','token'])

class CuraSnapmakerSenderPlugin(Extension,OutputDevicePlugin,QAbstractTableModel,QObject):
    autodiscoverychanged = pyqtSignal() 
    machineschanged = pyqtSignal()
    def __init__(self, parent = None) -> None:
        #Logger.log("d","Initializing CuraSnapmakerSenderPlugin")
        Extension.__init__(self)
        QObject.__init__(self)
        QAbstractTableModel.__init__(self)
        
        self.machines : List[machinePrototype] = list()

        self.setMenuName(i18n_catalog.i18nc("@item:inmenu", "CuraSnapmakerSender"))
        self.addMenuItem(i18n_catalog.i18nc("@item:inmenu", "Settings"), self.showSettings)
        self._view = None
        self.setPluginId("CuraSnapmakerSender")
        Application.getInstance().mainWindowChanged.connect(self.afterInit)
        Application.getInstance().applicationShuttingDown.connect(self.stop)
        self._settingsWindow = None
        self.settings = dict()
        self.settings["AutoDiscover"] = True
        self.settings["machines"] = list()
        self._active_added_Printers = list()
        self._active_discovered_Printers = list()
        self._tokenregistry = dict()
        self._stop_discovery_running = threading.Event()
        self._stop_discovery_running.clear()
        self._discoveryThread = None 
        self._stop_discovery_event = threading.Event()
        

       
    
    @pyqtSlot()
    def autodiscoverchanged_exec(self):
        #Logger.log("d","autodiscoverchanged_exec" + str(self.settings["AutoDiscover"]) + " " + str(self._discoveryThread.is_alive()))
        if(self.settings["AutoDiscover"] and not self._discoveryThread.is_alive()):
            #Logger.log("d","Auto-Discovery Enabled")
            self._discoveryThread = threading.Thread(target=self.timedDiscovering)
            self._discoveryThread.start()
        elif(not self.settings["AutoDiscover"] and self._discoveryThread and self._discoveryThread.is_alive()):
            #Logger.log("d","Auto-Discovery Disabled")
            self._stop_discovery_event.set()

        
    @pyqtProperty(bool)
    def autodiscover(self):
        #Logger.log("d","autodicover read")
        return self.settings["AutoDiscover"]

    
    @autodiscover.setter
    def autodiscover(self, autodiscover):
        #Logger.log("d","autodicover write")
        self.settings["AutoDiscover"] = autodiscover
        self.autodiscoverychanged.emit()
        #self._autodiscover = autodiscover


    def stop(self):
        self._stop_discovery_event.set()
        #Logger.log("d","Stopping everything from CuraSnapmakerSender")
        for printer_remove in self._active_added_Printers:
            self.removePrinter(printer_remove)
        for printer_remove in self._active_discovered_Printers:
            self.removePrinter(printer_remove)
        self.saveSettings()
        self.SaveTokenRegistry()

    def afterInit(self):
        #Logger.log("d","Log Something")
        self.loadTokenRegistry()
        self.loadSettings()
        self.autodiscoverychanged.connect(self.autodiscoverchanged_exec)
        if(self.settings["AutoDiscover"]):
            #Logger.log("d","Auto-Discovery Enabled")
            self._discoveryThread = threading.Thread(target=self.timedDiscovering)
            self._discoveryThread.start()
        self._manualprinters : List[machinePrototype] = list()
        for x in self.settings["machines"]:
            self._manualprinters.append(machinePrototype(x[0],x[1],x[2]))
        

        #Logger.log("d","Getting Item result : "+str(self._manualprinters.getItem(0)))
        self.managePrinters()

    def loadTokenRegistry(self):
        path = PluginRegistry.getInstance().getPluginPath(self.getPluginId())
        path = os.path.join(path,'tokens.cfg')
        if os.path.exists(path):
            self._tokenregistry = json.load(open(path,'r'))
        else:
            with open(path,'w') as file:
                json.dump(self._tokenregistry,file)
        Logger.debug("TokenRegistryLoaded")
        

    def SaveTokenRegistry(self):
        path = PluginRegistry.getInstance().getPluginPath(self.getPluginId())
        path = os.path.join(path,'tokens.cfg')
        with open(path,'w') as file:
            json.dump(self._tokenregistry,file)
        Logger.debug("TokensSaved")

    def loadSettings(self):
        path = PluginRegistry.getInstance().getPluginPath(self.getPluginId())
        path = os.path.join(path,'settings.cfg')
        if os.path.exists(path):
            self.settings = json.load(open(path,'r'))
        else:
            with open(path,'w') as file:
                json.dump(self.settings,file)
        Logger.debug("SettingsLoaded")
    @pyqtSlot()
    def saveSettings(self):
        path = PluginRegistry.getInstance().getPluginPath(self.getPluginId())
        arr = list()
        for x in self._manualprinters:
            arr.append(x)
        #Logger.log("d",arr)
        self.settings["machines"] = arr
        path = os.path.join(path,'settings.cfg')
        with open(path,'w') as file:
            json.dump(self.settings,file)#
        #Logger.log("d","SettingsSaved")
        
        
    
    def timedDiscovering(self):
        #Logger.log("d","Discovery thread started")
        while not self._stop_discovery_event.is_set():
            if not self.settings["AutoDiscover"]:
                #Logger.log("d","Discovery thread stopped")
                break
            self.discoverAndManagePrinters()
            self._stop_discovery_event.wait(5)
        self._stop_discovery_event.clear()
        #Logger.log("d","Discovery thread stopped")
    

    def discoverAndManagePrinters(self):
        old_printers = [x for x in self._active_discovered_Printers]
        printers_dict = discover_Snapmaker()
        printers = [x for x in printers_dict]
        for printer in printers:
            try:
                in_list = False
                for old_printer in old_printers:
                    if old_printer == printer:
                        #Logger.log("d","Already in list " + str(printer))
                        old_printers.remove(old_printer)
                        in_list = True
                if not in_list:   
                    raise ValueError
            except ValueError:
                if not self.addPrinter(printer):
                    printers.remove(printer)
        for printer_remove in old_printers:
            self.removePrinter(printer_remove)
        self._active_discovered_Printers = [x for x in printers]
    @pyqtSlot()
    def managePrinters(self):
        #Logger.log("d","Managing manually added printers")
        old_printers = [x for x in self._active_added_Printers]
        printers = self._manualprinters
        for printer in printers:
            try:
                in_list = False
                for old_printer in old_printers:
                    if old_printer == printer:
                        #Logger.log("d","Already in list " + str(printer))
                        old_printers.remove(old_printer)
                        in_list = True
                if not in_list:   
                    raise ValueError
            except ValueError:
                if not self.addPrinter(printer):#manually added printers take priority, so throw the already added printer from discovery out
                    self.removePrinter(printer)
                    in_list = False
                    for old_printer in self._active_discovered_Printers:
                        if old_printer.address == printer.address:
                            #Logger.log("d","Already in list " + str(printer))
                            self._active_discovered_Printers.remove(old_printer)
                            in_list = True
                    if not self.addPrinter(printer):#and add the manual version 
                        #raise Exception("Problem with manually added printer")
                        to_remove = [[record.a, record.b] for record in self._manualprinters if record.address == printer.address][0]
                        self._manualprinters.remove(to_remove)
                #Logger.log("d","Added manually " + str(printer))
        for printer_remove in old_printers:
            #Logger.log("d","Removed " + str(printer_remove))
            self.removePrinter(printer_remove)
        self._active_added_Printers = [x for x in printers]

    def addPrinter(self, printer):
        #Logger.log("d","Adding "+printer['name']+printer['address']+ " OutputDevice")
        token = ''
        if printer.address in self._tokenregistry:
           token = self._tokenregistry[printer.address]
        if self.getOutputDeviceManager().getOutputDevice(printer.address):
            return False #already added
        else:
            self.getOutputDeviceManager().addOutputDevice(CuraSnapmakerSenderOutputDevice(printer.address,printer.name,token=token))
            return True

    def removePrinter(self, printer_remove:Dict):
        
        printer = self.getOutputDeviceManager().getOutputDevice(printer_remove.address)
        # STore the token in the tokenregistry, maybe we can reuse it
        try:
            self._tokenregistry[printer_remove.address]= printer.token
        except AttributeError:
            pass
        printer.tearDown()
        self.getOutputDeviceManager().removeOutputDevice(printer.getId())
        #Logger.log("d","Removing "+printer_remove['name']+printer_remove['address']+ " OutputDevice")

    def showSettings(self):
        if not self._settingsWindow:
            self._settingsWindow =self._createSettingsDialogue()
        self._settingsWindow.show()
        
    
    def _createSettingsDialogue(self) -> QQuickWindow:
        qml_file_path = os.path.join(PluginRegistry.getInstance().getPluginPath(self.getPluginId()), "CuraSnapmakerSenderSettings.qml")
        component = Application.getInstance().createQmlComponent(qml_file_path,{"manager": self})
        print(component)
        return component

    @pyqtSlot()
    def _appendEmptyPrinter(self):
        self.beginInsertRows(QModelIndex(),self.rowCount(QModelIndex()),self.rowCount(QModelIndex()))
        Logger.debug(str(len(self._manualprinters)))
        self._manualprinters.append(machinePrototype('MySnapmaker'+ str(len(self._manualprinters)+1),'192.168.0.'+str(len(self._manualprinters)+1),''))
        Logger.debug(str(len(self._manualprinters)))
        
        self.endInsertRows()
    @pyqtSlot(int)
    def _removePrinterfromList(self, index:int):
        self.beginRemoveRows(QModelIndex(),index,index)
        self._manualprinters.pop(index-1)
        self.endRemoveRows()
    @pyqtSlot(str)
    def headerData(self, section: int, orientation: Qt.Orientation, role: int = ...) -> typing.Any:
        Logger.debug("HeaderData")
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                if section == 0:
                    return "Name"
                else:
                    return "Address(IPv4,IPv6,Hostname)"
        return False

    def rowCount(self, index):
        Logger.debug(len(self._manualprinters)+1)
        return len(self._manualprinters)+1

    def columnCount(self, index):
        return int(2)

    @pyqtSlot(QModelIndex,Qt.ItemDataRole,result=QVariant)
    def data(self, index, role):
        Logger.debug("Role: "+str(role))
        if not index.isValid():
            return QVariant()
       
        if role == Qt.ItemDataRole.DisplayRole or role == Qt.ItemDataRole.EditRole:
            if index.row() == 0 :
                if index.column() == 0:
                    value = "Name"
                else :
                    value = "IP-Address"
                return value
            myvalue = self._manualprinters[index.row()-1]
            if index.column() == 0:
                value = myvalue.name
            else :
                value = myvalue.address
            return str(value)
        return QAbstractTableModel.data(index,role)

    def setData(self, index, value, role):
        if index.row() == 0 :
            return False
        if role == Qt.EditRole:
            try:
                value = str(value)
            except ValueError:
                return False
            if index.column() == 0:
                self._manualprinters[index.row()-1].name = value
            else :
                self._manualprinters[index.row()-1].address = value
            return True
        return False
    @pyqtSlot(QModelIndex,result=Qt.ItemFlag)
    def flags(self, index):
        Logger.debug("Flags")
        if index.row() == 0:
            return super().flags(index)
        return super().flags(index) | Qt.ItemFlag.ItemIsEditable | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        #return Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | 
    def roleNames(self) -> typing.Dict[int, 'QByteArray']:
        names = super().roleNames()
        Logger.debug(names)
        return names

                
       
class CuraSnapmakerSenderOutputDevice(OutputDevice): #We need an actual device to do the writing.
    def __init__(self,uri:str,name:str,token=''):
        super().__init__("CuraSnapmakerSenderOutputDevice") #Give an ID which is used to refer to the output device.
        self._nameofSnapmaker = name
        self._uri = uri
        self._id = uri
        #Optionally set some metadata.
        self.setName("CuraSnapmakerSender") 
        self.setShortDescription(i18n_catalog.i18nc("@message", "Send To ")+self._nameofSnapmaker) #This is put on the save button.
        self.setDescription(i18n_catalog.i18nc("@message", "Send To ")+self._nameofSnapmaker)
        self.setIconName("save")

        self._token = token
        self._printer = SnapmakerApiV1.SnapmakerApiV1(self._uri,self._token)
        self._authrequired_message = Message(i18n_catalog.i18nc("@message", "Awaiting Authorization.\r\nPlease allow the connection on your Snapmaker."),dismissable=False)
        self._authrequired_message.addAction("abort",i18n_catalog.i18nc("@button","Abort"),icon ="abort",description=i18n_catalog.i18nc("@message:description","Abort Sending..."))
        self._authrequired_message.actionTriggered.connect(self.abortSend)
        self._connect_failed_message = Message(i18n_catalog.i18nc("@message", "Could not connect to your machine. It is either off, the given address is wrong or not reachable or your Snapmaker refused the connection."),lifetime=30,dismissable=True,title='Error')
        self._prepare_send_message = Message(i18n_catalog.i18nc("@message", "Preparing Gcode for sending, please wait."),dismissable=True,title='Info')
        self._progress_message = Message(i18n_catalog.i18nc("@message", "Sending file to ")+ self._nameofSnapmaker)

    def requestWrite(self, nodes, file_name = None, limit_mimetypes = None, file_handler = None, **kwargs):
        #Logger.log("d","Firing Timer")
        self._writeHandleTimer = QTimer()
        self._writeHandleTimer.timeout.connect(lambda: self.handleWrite(nodes,file_name,limit_mimetypes,file_handler))
        self._writeHandleTimer.setInterval(1)
        self._writeHandleTimer.setSingleShot(True)
        self._writeHandleTimer.start()
    def abortSend(self,message,action):
        message.hide()
        if(self._printer.state != SnapmakerApiV1.SnapmakerApiState.NOTCONNECTED or self._printer.state != SnapmakerApiV1.SnapmakerApiState.FATAL):
            self._printer.disconnect()
        self._writeHandleTimer.stop()
    def handleWrite(self, nodes, file_name = None, limit_mimetypes = None, file_handler = None, **kwargs):
        #Logger.log("d","In handleWrite")
        self._writeHandleTimer.setInterval(1000)
        result = None
        if not self._printer.state == SnapmakerApiV1.SnapmakerApiState.IDLE:
            if(self._printer.state == SnapmakerApiV1.SnapmakerApiState.NOTCONNECTED):
                result = self._printer.connect()
                if result == False:
                    self.writeError.emit()
                    self._connect_failed_message.show()
                    return
            elif(self._printer.state == SnapmakerApiV1.SnapmakerApiState.FATAL):
                #Logger.log("d",self._printer.state)
                self._printer = SnapmakerApiV1.SnapmakerApiV1(self._uri,self._printer.token)
                result = self._printer.connect()
                if result == False:
                    self.writeError.emit()
                    self._connect_failed_message.show()
                    return
            elif(self._printer.state == SnapmakerApiV1.SnapmakerApiState.AWAITING_AUTHORIZATION):
                #Logger.log("d",self._printer.state)
                self._authrequired_message.show()
            else:
                #Logger.log("d",self._printer.state)
                self.writeError.emit()
                message = Message(i18n_catalog.i18nc("@message", "Sending failed, try again later"),lifetime=30,dismissable=True,title='Error')
                message.show()
                return
            
            self._writeHandleTimer.start()
            return
        #Logger.log("d","Ready to send")    
        self._authrequired_message.hide()
        self._prepare_send_message.show()
        self._token = self._printer.token
        self.writeStarted.emit(self)
        print_info = CuraApplication.getInstance().getPrintInformation()
        gcode_writer = MeshWriter()
        self._gcode_stream = StringIO()
        #In case the Plugin Gcodewriter is a separate Plugin
        #try:
        #gcode_writer = cast(MeshWriter, PluginRegistry.getInstance().getPluginObject("CuraSnapmakerSender"))
        #except UM.PluginError.PluginNotFoundError:
        #gcode_writer = cast(MeshWriter, PluginRegistry.getInstance().getPluginObject("GCodeWriter"))
        gcode_writer=SnapmakerGCodeWriter.SnapmakerGCodeWriter()
        if not gcode_writer.write(self._gcode_stream, None):
            #Logger.log("e", "GCodeWrite failed: %s" % gcode_writer.getInformation())
            return
        self.content_length = self._gcode_stream.tell()
        self._gcode_stream.seek(0)
        self._byteStream = BytesIOWrapper(self._gcode_stream)
        self._printer.setBlocking(False)
        self.active_sending_future = self._printer.send_gcode_file(print_info.jobName.strip()+".gcode",self._byteStream,callback=self.updateProgress)
        self.active_sending_future.add_done_callback(self.transmitDone)
        self._printer.setBlocking(True)
        self._progress_message.setMaxProgress(100)
        self._progress_message.setProgress(0)
        self._progress_message.show()
        #Logger.log("d","WriteRequested")

        

    def updateProgress(self,monitor):
        ##Logger.log("d",str(monitor.bytes_read) +" of " + str(self.content_length))
        self._prepare_send_message.hide()
        self._progress_message.setProgress((monitor.bytes_read/self.content_length) * 100)
        self.writeProgress.emit()
            

    def transmitDone(self,future):
        #Logger.log("d","WriteDone")
        self._progress_message.hide()
        if self.active_sending_future.result():
            self.writeFinished.emit()
            self.writeSuccess.emit()
        else:
            self.writeError.emit()

        print_name = CuraApplication.getInstance().getPrintInformation().jobName
        message = Message(
           i18n_catalog.i18nc("@message", "Successfully sent '%s' to %s") % (print_name, self._nameofSnapmaker),
           lifetime=30,dismissable=True,title='Success')
        message.show()

        # Disconnect after upload so user can operate printer to select file.
        self._printer.setBlocking(False)
        self._printer.disconnect()
        self._printer.setBlocking(True)
        self._printer = SnapmakerApiV1.SnapmakerApiV1(self._uri,self._token)

    def tearDown(self):
        self._printer.disconnect()

        
def discover_Snapmaker() :
    #Logger.log("d", "Discovering Snapmaker")
    sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(5)
    to_return=[]
    message = 'discover'
    address = ('<broadcast>',20054)
    sock.sendto(message.encode(),address)
    try:
        while True:
            data,server = sock.recvfrom(4096)
            response = data.decode()
            datasplit = response.split('|')
            printer = machinePrototype('','','')
            printer.name,printer.address = datasplit[0].split('@')
            to_log = "Found: "+printer.name+"("+printer.address+")"
            Logger.log("d", to_log)
            for token in datasplit[1:]:
                identifier,value = token.split(':')
                printer[identifier]=value
            to_return.append(printer)

    except socket.timeout:
        pass
    #Logger.log("d", "Finished discovering Snapmaker")
    sock.close()
    return to_return

class BytesIOWrapper:
    def __init__(self, string_buffer, encoding='utf-8'):
        self.string_buffer = string_buffer
        self.encoding = encoding

    def __getattr__(self, attr):
        return getattr(self.string_buffer, attr)

    def read(self, size=-1):
        content = self.string_buffer.read(size)
        return content.encode(self.encoding)

    def write(self, b):
        content = b.decode(self.encoding)
        return self.string_buffer.write(content)
