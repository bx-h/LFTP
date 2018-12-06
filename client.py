# -*- coding: utf-8 -*-
import Lftp
import Event
import sys
import ntpath
import time
from vsftp import VsPacket
import Logging
import re

UDP_IP = "0.0.0.0"
UDP_PORT = 0  # 假如填0，由系统随机分配端口
UPD_DESTINATION = 5005

class FileSender:
    files = []
    timeStarted = Event.getCurrentMills()
    
    def __init__(self, fileName, addresses, RType):
        self.fileName = fileName
        self.addresses = addresses
        self.RType = RType
        self.packetcount = 0
        self.filehH = None
        
    def send(self):  #把send拆分为preSend
        self.lftpSocket = Lftp.createSocket(UDP_IP, UDP_PORT)
        
        for desination in self.addresses:
            self.lftpSocket.addPeer(desination)
        
        ''' 发送开始包'''
        vsFtpPacket = VsPacket()
        vsFtpPacket.type = VsPacket.TYPE_BEGIN
        if (self.RType == "get"):
            vsFtpPacket.Rt = VsPacket.RT_GET
        elif (self.RType == "put"):
            vsFtpPacket.Rt = VsPacket.RT_PUT
        vsFtpPacket.data = FileSender.processFileName(self.fileName)

        if self.lftpSocket.sendToAll(vsFtpPacket.pack()) == False:
            print("Transmission error, quiting")
            sys.exit()

        if (self.RType == "get"):
            self.filehH = open(self.fileName, 'w')
            Lftp.registerReceiveHandler(self.lftpSocket, self.receiveHandler2)
            print("Started Receiver on  " + str(self.lftpSocket.socket.getsockname()))
            # self.filehH = open(self.fileName, 'w')

        elif (self.RType == "put"):
            fileToSend = open(self.fileName)
            print("Openned fileToSend DF:" + str(fileToSend.fileno()) + " name: " + str(self.fileName))
            Lftp.registerEventHandler(self.lftpSocket, fileSender.handleEvent)
            Event.eventFd(fileToSend.fileno(), self.handleFileDataAvailable, fileToSend, "FileDataAvailable")
        
    def handleFileDataAvailable(self, fd, fileToSend):      
        data = fileToSend.read(800)
        if data:
            vsFtpPacket = VsPacket()
            vsFtpPacket.type = VsPacket.TYPE_DATA
            vsFtpPacket.data = data
            if self.lftpSocket.sendToAll(vsFtpPacket.pack()) == False:
                print("Transmission error, quiting")
                sys.exit()   
            self.packetcount  = self.packetcount + 1
            print("### " + str(self.packetcount))
        else:
            ''' Send END packet'''
            vsFtpPacket = VsPacket()
            vsFtpPacket.type = VsPacket.TYPE_END
            vsFtpPacket.data = data
            if self.lftpSocket.sendToAll(vsFtpPacket.pack()) == False:
                print("Transmission error, quiting")
            Event.eventFdDelete(self.handleFileDataAvailable, fileToSend)
            print("File " + self.fileName + " sent")
            Lftp.closeSocket(self.lftpSocket)
            # sys.exit(0)


    def receiveHandler2(self, lftpSocket, senderAddress, data):
        packet = VsPacket().unpack(data)
        print(">> " + str(packet))
        
        ''' Get or create file info object'''
        if packet.type == VsPacket.TYPE_DATA:
            self.filehH.write(str(packet.data))
            pass
        elif packet.type == VsPacket.TYPE_END:
            print("GOT PACKET END, closing file")
            self.filehH.close()
            Lftp.closeSocket(self.lftpSocket)
            pass  
        pass
            
    def handleEvent(self, lftpSocket, eventType):
        if eventType == Event.TYPE_TIMEOUT:
            sys.exit("TimeOut event received")
        if eventType == Event.TYPE_CLOSED:
            print("Socket closed event received on " + str(lftpSocket))
            print("Lost Packets:" + str(lftpSocket.packetloss))
            print("Sent Data packets:" + str(lftpSocket.packetsSentData))
            print("Sent Control packets:" + str(lftpSocket.packetsSentControl))
            print("Received packets(total):" + str(lftpSocket.packetsReceived))
            print("Received data packets:" + str(lftpSocket.packetsReceivedData))
            print("Received and skipped packets:" + str(lftpSocket.packetsReceivedIgnored))
            print("Fake loss:" + str(lftpSocket.packetFakeLoss))
            print("Time taken: " + str((Event.getCurrentMills() - self.timeStarted)))
            
    @staticmethod
    def processFileName(path):
        head, tail = ntpath.split(path)
        return tail or ntpath.basename(head)


if __name__ == '__main__':
    hosts = []
    # files = []
    cmd = input("command: ")
    CL = cmd.split()
    filename = CL[3]

    if CL[1] == "lget":
        RType = "get"
    elif CL[1] == "lsend":
        RType = "put"

    hostGroup = re.search('([0-9]+(?:\.[0-9]+){3}):([0-9]+)', CL[2])  # 匹配正则表达式
    host = hostGroup.group(1)
    port = hostGroup.group(2)
    print("Found host:" + host + " port:" + port)
    print("found file: " + filename)
    hosts.append((hostGroup.group(1), int(hostGroup.group(2))))
    # sys.argv is a list in Python, which contains the command-line arguments passed to the script.
    
    #print("Will send files:" + str(files) + " to hosts:" + str(hosts)) # 打印将要发送的文件到哪个host
    
    Logging.Logger.setFile("client.log") # log为输出文件？setFile指以w格式打开文件，并付给logger的file参数
    #for fileToSend in files:

    fileSender = FileSender(filename, hosts, RType)
    fileSender.send() # 循环发送文件
    Event.eventLoop()



        



    
#For unpacking we first need to know the size of the data

#eceivedPacker = LftpPacket().unpack(packet.pack());
#print receivedPacker

#print "Secnum:" + str(receivedPacker.seqnum) + " Data length:" + str(receivedPacker.datalength)
#print "Data:" + receivedPacker.data
