from enum import Enum
from pickle import FALSE
import requests
import socket
from typing import Dict, List, Optional, Union
import logging
import os
import threading
import queue
import concurrent.futures

from requests.sessions import session
from .encoder import MultipartEncoder,MultipartEncoderMonitor
from UM.Logger import Logger


'''# import the included version of requests-toolbelt
import sys
import importlib.util

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "requests_toolbelt"))

toolbelt_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "requests_toolbelt",  "__init__.py"
)
spec = importlib.util.spec_from_file_location("requests_toolbelt", toolbelt_path)
requests_toolbelt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(requests_toolbelt)

del sys.path[-1] # restore original path

MultipartEncoder = requests_toolbelt.MultipartEncoder
MultipartEncoderMonitor = requests_toolbelt.MultipartEncoderMonitor'''

def discover_Snapmaker() -> List[str] :
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
            printer = {}
            printer['name'],printer['address'] = datasplit[0].split('@')
            for token in datasplit[1:]:
                identifier,value = token.split(':')
                printer[identifier]=value
            to_return.append(printer)

    except socket.timeout:
        pass
    sock.close()
    return to_return

class SnapmakerApiState(Enum):
    INIT = 0 
    '''nothing has happened yet'''
    NOTCONNECTED = 1 
    '''needs connecting'''
    SENDING_FILE = 2 
    '''sending a file'''
    SENDING_GCODE = 3 
    '''sending Gcode'''
    IDLE = 4 
    '''ready to work with the commands'''
    AWAITING_AUTHORIZATION = 5 
    '''connected, but not yet able to control (confirmation on screen)'''
    GETTING_STATUS = 6 
    '''getting the status'''
    DISCONNECTING = 7 
    '''in process of Disconnecting'''
    FATAL = 99 
    '''A non healable state'''

class _SnapmakerTasks(Enum):
    DISCONNECT = 0
    SEND_FILE = 1
    SEND_GCODE = 2

class _SnapmakerWorkToDo():
    def __init__(self):
        self.task = _SnapmakerTasks.DISCONNECT
        self.future = concurrent.futures.Future()

class _SnapmakerSendFileTask(_SnapmakerWorkToDo):
    def __init__(self):
        super().__init__()
        self.fileio = str()
        self.filename = str()
        self.callback = None

class _SnapmakerSendGCode(_SnapmakerWorkToDo):
    def __init__(self):
        super().__init__()
        self.gcode = str()

class SnapmakerApiV1(threading.Thread):
    '''
    Class for handling communication to a Snapmaker machine.

    Constructor SnapmakerApiV1(uri,token)
    uri: URL of the Snapmaker as str. Can be an IPV4, IPV6 or even a hostname
    token: Is a string. Defaults to an empty string. Token is used by the Snapmaker to tell, if the User-Authorization(on the touchscreen) has already
    happened. So if you want to reuse a Connection just read the token property of a authorized Connection and supply it here again. 
    When turning the Snapmaker machine off, all authorized tokens get deleted.

    Use the state variable to wait for the authorization(Just Wait for SnapmakerState.IDLE).
    '''
    #state : SnapmakerApiState = SnapmakerApiState.INIT
    #conn : http_client.HTTPConnection
    #_machine_info : Dict
    #_status : Dict
    #_session : requests.Session
    #_log : logging.Logger
    #token : str
    #_uri : str
    #_threadConditionObject : threading.Condition
    #_blocking : bool #determines the behavior, if true the function block and Return on success. If False, the functions return a promise 
    #_workQue : queue.Queue

    def __init__(self,uri:str,token=''):
        if(len(uri) == 0):
            raise ValueError("Empty URI not allowed!")
        super().__init__()
        #self._log = logging.getLogger("SnapmakerApiV1")
        self._log = Logger
        #self._log.setLevel(logging.DEBUG)
        self._log.info("INIT SnapmakerApiClass")
        self._uri = uri
        self._status = {}
        self._machine_info = {}
        self.state = SnapmakerApiState.NOTCONNECTED
        self._session = requests.session()
        self.token = token
        self._workQue = queue.Queue(1)
        self._blocking = True
        self._threadConditionObject = threading.Condition(None)
        self._threadConditionObject.acquire()
        self.running = False
    def setBlocking(self,block : bool) -> None:
        '''
        Allows to set the behaviour of the Api. 

        If set to True, all calls will block, until the result is ready. 
        If set to False, a concurrent.future gets returned.
        '''
        self._blocking = block
    def connect(self) -> bool:
        '''
        Function for issuing a connect.

        Retrurns True if connection is successful(but not yet authorized).
        Returns False, if a error happened. Will raise Exceptions, when the underlying requests library raises those.

        Starts the management thread of the connection.
        '''
        self._log.debug("Connecting...")            
        #self.conn = http_client.HTTPConnection(self.uri,8080,timeout=3.0)
        #self.conn.request('POST','/api/v1/connect',,{'Content-Type': 'application/x-www-form-urlencoded'})
        try:
            resp =self._session.post("http://"+self._uri+":8080/api/v1/connect",data="token="+self.token,headers={'Content-Type': 'application/x-www-form-urlencoded'},timeout=1.0)
        except (ConnectionError,TimeoutError, requests.exceptions.ConnectTimeout):
            return False
        #response = self.conn.getresponse()
        if resp.status_code == requests.codes.ok :
            
            self._log.debug("Connection established, checking if Authorization necessesary")
            self._machine_info=resp.json()
            self._log.info(self._machine_info)
            self.token = self._machine_info['token']
            self._threadConditionObject = threading.Condition()
            while not self._workQue.empty():
                self._workQue.get(True)
            try:
                result = self._get_status()
            except Exception as e:
                self.state = SnapmakerApiState.FATAL
                self.running = False
                self._log.debug('Exception in SnapmakerApi:')
                self._log.debug(e)
                self._log.debug('Thread SnapmakerApi finished')
                return
            else:
                if result is None:
                    self.state = SnapmakerApiState.FATAL
                    self.running = False
                    self._log.debug('No result gotten')
                    self._log.debug('Thread SnapmakerApi finished')
                    return FALSE
                elif result == 204:
                    self.state = SnapmakerApiState.AWAITING_AUTHORIZATION
                else:
                    self.state = SnapmakerApiState.IDLE
            self.start()
            return True
        elif resp.status_code == 403:
            if self.token != '':
                self.token = ''
                return self.connect()
            else :
                return False
        else:
            resp.raise_for_status()
            return False
    def disconnect(self) -> Union[concurrent.futures.Future, bool] :
        '''
        Function for issueing a disconnect.

        Returns a future, if setBlocking(False).

        Returns True, if disconnect successful.
        Returns False, if some kind of unexpected behaviour occured.

        Stops in every case the management thread.
        '''
        if(self.running):
            workToDo = _SnapmakerWorkToDo()
            workToDo.task = _SnapmakerTasks.DISCONNECT
            workToDo.future = concurrent.futures.Future()
            self._workQue.put(workToDo)
            if self._blocking:
                return workToDo.future.result(None)
            else:
                return workToDo.future
        else:
            return False
    def _disconnect(self) -> bool:
        self._log.debug("Disconnecting...")
        #self.conn = http_client.HTTPConnection(self.uri,8080,timeout=3.0)
        #self.conn.request('POST','/api/v1/disconnect',f"token={self.token}",{'Content-Type': 'application/x-www-form-urlencoded'})        
        #response = self.conn.getresponse()
        resp =self._session.post("http://"+self._uri+":8080/api/v1/disconnect",data="token="+self.token,headers={'Content-Type': 'application/x-www-form-urlencoded'})
        if resp.status_code == requests.codes.ok :
            self._log.debug("Disconnect successful")
            self._session.close()
            return True
        else:
            resp.raise_for_status()
            #self.conn.close()
            return False


    def _get_status(self) -> Optional[int]:
        #self.conn = http_client.HTTPConnection(self.uri,8080,timeout=3.0)
        #self.conn.request('GET',f'/api/v1/status?token={self.token}')
        #response = self.conn.getresponse()
        resp = self._session.get("http://"+self._uri+":8080/api/v1/status?token="+self.token)
        if resp.status_code == requests.codes.ok:
            self._status=resp.json()
            return resp.status_code
        elif resp.status_code  == 204:#nocontent
            self._log.debug('Waiting for authoritzation')
            return resp.status_code
        elif resp.status_code  == 401:#Authorization denied
            self._log.debug('Authorization denied')
            self._session.close()
            return None
        else:
            resp.raise_for_status()
            return resp.status_code
        
    def run_GCode(self,gcode:str) -> Union[concurrent.futures.Future,bool]:
        '''
        Function for execution of Gcode.

        Returns a future, if setBlocking(False).

        Returns True, if Gcode was executed successfully.
        Returns False, if some kind of unexpected behaviour occured.

        Unfortunately Snapmaker does not return any Output of the execution.
        '''
        if not self.running:
            return False
        workToDo = _SnapmakerSendGCode()
        workToDo.task = _SnapmakerTasks.SEND_FILE
        workToDo.future = concurrent.futures.Future()
        workToDo.gcode = gcode
        self._workQue.put(workToDo)
        if self._blocking:
            return workToDo.future.result(None)
        else:
            return workToDo.future
    def _run_GCode(self,gcode:str) -> bool:
        resp =self._session.post("http://"+self._uri+":8080/api/v1/execute_code",data="token="+self.token+"&code="+gcode,headers={'Content-Type': 'application/x-www-form-urlencoded'})
        if resp.status_code == requests.codes.ok :
            self._log.debug("Ran Gcode "+gcode+" successful")
            return True
        else:
            resp.raise_for_status()
            return False
    '''def run_Gcode_string(self,gcode:str) -> Optional[bool]:
        if gcode.find("\r\n") != -1 :
            lines = gcode.split("\r\n")
        elif gcode.find("\n") != -1 :
            lines = gcode.split("\n")
        else:
            lines = [gcode]
        return self.run_GCode_lines(lines)'''
    def send_gcode_file(self,name,fileio,callback=None) -> Union[concurrent.futures.Future,bool]:
        '''
        Function for sending a file.

        file_path needs to be a string.(For open() function)



        Returns a future, if setBlocking(False).

        Returns True, if File was sent completely.
        Returns False, if some kind of unexpected behaviour occured.
        '''
        if not self.running:
            return False
        workToDo = _SnapmakerSendFileTask()
        workToDo.task = _SnapmakerTasks.SEND_FILE
        workToDo.future = concurrent.futures.Future()
        workToDo.fileio = fileio
        workToDo.filename = name
        workToDo.callback = callback
        self._workQue.put(workToDo)
        if self._blocking:
            return workToDo.future.result(None)
        else:
            return workToDo.future
    def _send_gcode_file(self,filename:str,fileio,callback=None):
        self._log.debug("in _send_gcode_file")
        files = {'token' : (None,self.token),
            'file': (filename, fileio, 'application/octet-stream')}
        e = MultipartEncoder(files)
        m = MultipartEncoderMonitor(e,callback=callback)
        
        #files = {'file': (filename, fileio.getvalue(), 'application/octet-stream')}
        resp = self._session.post("http://"+self._uri+":8080/api/v1/upload?token="+self.token,data=m,headers={'Content-Type': m.content_type})
        if resp.status_code == requests.codes.ok :
            self._log.debug("Uploaded file "+filename+" successful")
        else:
            resp.raise_for_status()
    def run(self):
        self._log.debug('Thread SnapmakerApi started')
        self.running = True
        
        while True:
            try :
                task = self._workQue.get(True,1)
                if task.task == _SnapmakerTasks.SEND_FILE:
                    send_file_task = task
                    if send_file_task.future.set_running_or_notify_cancel():
                        self.state = SnapmakerApiState.SENDING_FILE
                        try:
                            self._log.debug("in Sending Task")
                            self._log.debug(send_file_task)
                            send_file_task.future.set_result(self._send_gcode_file(send_file_task.filename,send_file_task.fileio,callback=send_file_task.callback))
                        except Exception as e:
                            send_file_task.future.set_exception(e)
                            self.state = SnapmakerApiState.FATAL
                            break
                        self.state = SnapmakerApiState.IDLE
                elif task.task == _SnapmakerTasks.SEND_GCODE:
                    gcode_task = task
                    if gcode_task.future.set_running_or_notify_cancel():
                        self.state = SnapmakerApiState.SENDING_GCODE
                        try:
                            gcode_task.future.set_result(self._run_GCode(gcode_task.gcode))
                        except Exception as e:
                            gcode_task.future.set_exception(e)
                            self.state = SnapmakerApiState.FATAL
                            break
                        self.state = SnapmakerApiState.IDLE
                    self._run_GCode(gcode_task.gcode)
                elif task.task == _SnapmakerTasks.DISCONNECT:
                    disconnect_task  = task
                    if disconnect_task.future.set_running_or_notify_cancel():
                        try:
                            if self._disconnect():
                                disconnect_task.future.set_result(True)
                                self.state = SnapmakerApiState.NOTCONNECTED
                                break
                            else:
                                disconnect_task.future.set_result(False)
                                self.state = SnapmakerApiState.FATAL
                                break
                        except Exception as e:
                            disconnect_task.future.set_exception(e)
                            break
            except queue.Empty:
                try:
                    result = self._get_status()
                except Exception as e:
                    self.state = SnapmakerApiState.FATAL
                    break
                else:
                    if result is None:
                        self.state = SnapmakerApiState.FATAL
                        break#We cannot fix this, as user denied Auth
                    elif result == 204:
                        self.state = SnapmakerApiState.AWAITING_AUTHORIZATION
                    else:
                        self.state = SnapmakerApiState.IDLE
        self.running = False
        self._log.debug('Normal Exit Snapmaker Api')
        self._log.debug('Thread SnapmakerApi finished')
            

