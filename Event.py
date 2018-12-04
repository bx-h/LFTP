# -*- coding: utf-8 -*-


import time
import select
import sys
from Logging import Logger
from Logging import Level

TYPE_TIMEOUT = 1
TYPE_CLOSED = 2
EVENT_TYPE_FD = 1
EVENT_TYPE_TIME = 2

events = []
logger = Logger("EVENT", Level.INFO)

def getCurrentMills():
    return int(round(time.time() * 1000))

def eventTimeout(timeMs, callback, argument, strId):    
    event = EventData(EVENT_TYPE_TIME, callback, argument)
    event.time = getCurrentMills() + timeMs
    event.id = strId
    logger.log(Level.DEBUG, "Registering timeout " + str(event)) 
    events.append(event)

def eventTimeoutDelete(callback, argument):
    for event in events:
        if event.type == EVENT_TYPE_TIME and event.callback == callback and event.argument == argument:
            logger.log(Level.DEBUG, "Deleting " + str(event))
            events.remove(event)
            return True
    return False

def eventFd(fd, callback, callbackArgument, strId):
    logger.log(Level.DEBUG, "EVENT_FD Registered fd:" + str(fd))
    event = EventData(EVENT_TYPE_FD, callback, callbackArgument)
    event.fd = fd
    # file descriptor,
    # A file descriptor is either a socket or file object,
    # or a small integer gotten from a fileno() method call on one of those.
    # in lftp.py createSocket() has one usage :
    # Event.eventFd(sock.fileno(), handleDataAvailable, lftpSocket, "DataReceived")
    # fileno() 方法返回一个整型的文件描述符(file descriptor FD 整型)，可用于底层操作系统的 I/O 操作
    event.id = strId
    events.append(event)
    pass

def eventFdDelete(callback, argument):
    for event in events:
        if event.type == EVENT_TYPE_FD and event.callback == callback and event.argument == argument:
            events.remove(event)
            return True
    return False

def eventLoop():
    LOOP_DELAY = 0.001
    while True:
        if len(events) < 1:
            break
        for event in events:
            if event.type == EVENT_TYPE_FD:
                #print "Found:" + str(event)
                # Check if we have some data available
                oRead, [],  [] = select.select([event.fd], [], [], 0) # 0 - means polling, othewrise timeout time in seconds
                # select(rlist, wlist, xlist[, timeout]) -> (rlist, wlist, xlist)
                # rlist，wlist，xlist分别代表等待可读，可写，可读可写的文件的打开。不需要的项传[]
                # 第四个参数是timeout的时间，不指定则永远不会timeout
                # 返回值与参数一一对应

                if len(oRead) > 0:
                    event.callback(event.fd, event.argument)
                else:
                    #sys.stdout.write('.')
                    time.sleep(LOOP_DELAY)
            elif event.type == EVENT_TYPE_TIME:
                logger.log(Level.DEBUG, "Checking for timeout, current time:" + str(getCurrentMills()) + " event timeout:" + str(event.time) + " id:" + str(event.id))
                if event.time < getCurrentMills():
                    logger.log(Level.ERROR, "\n\nTIMEOUT for event: " + str(event)) 
                    event.callback(event.argument)

class EventData:
    def __init__(self, eventType, eventCallback, eventArgument):           
        self.type = eventType
        self.callback = eventCallback
        self.argument = eventArgument
        self.fd = None # to be set outside constructor
        self.time = None # to be set outside constructor
        self.id = None
    def __str__(self):  # Override string representation
        return "Type:" + str(self.type) + " argument:" + str(self.argument) + " callback:" + str(self.callback)
    

