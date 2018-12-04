# -*- coding: utf-8 -*-

import Lftp
import Event
from vsftp import VsPacket
import time
import sys
import Logging

def getCurrentMills():
    return int(round(time.time() * 1000))

class Receiver:
    files = []

    def __init__(self, host, port):
        self.port = port
        self.host = host
        self.packetcount = 0
        self.validPort = port + 1
    
    def start(self):
        self.lftpSocket = Lftp.createSocket(self.host, self.port)
        Lftp.registerReceiveHandler(self.lftpSocket, self.prereceiveHandler)
        print("Started Receiver on  " + str(self.lftpSocket.socket.getsockname()))
        Event.eventLoop()   
        


    def prereceiveHandler(self, lftpSocket, senderAddress, data):
        packet = VsPacket().unpack(data)
        print(">> " + str(packet))
        
        ''' Get or create file info object'''
        
        ''' Handle different VSFTP pacekt types'''
        if packet.type == VsPacket.TYPE_BEGIN:
            #func = packet.data.split('/')[0]
            filename = packet.data

            if packet.Rt == VsPacket.RT_GET:
                newR = Lftp.createSocket(self.host, self.validPort)
                self.validPort = self.validPort + 1
                newR.addPeer(senderAddress)
                fileToSend = open(filename)
                Event.eventFd(fileToSend.fileno(), self.handleFileDataAvailable, (fileToSend, newR), "FileDataAvailable")

            elif packet.Rt == VsPacket.RT_PUT:
                fileInfo = None
                for fInfoTmp in self.files:
                    if fInfoTmp.sender == senderAddress:
                        fileInfo = fInfoTmp
                if fileInfo is None:
                    fileInfo = FileInfo()
                    fileInfo.sender = senderAddress
                    self.files.append(fileInfo)
                Lftp.registerReceiveHandler(self.lftpSocket, self.receiveHandler)

                if fileInfo.filename is not None:
                    print("File already open !!!!")
                    sys.exit(1)
                print("GOT PACKET BEGIN, openning fileToWrite for writing:" + str(filename))
                fileInfo.filename = filename
                fileInfo.filehandle = open(filename,'w')
                fileInfo.sendStarted = Event.getCurrentMills()
            pass

    def handleFileDataAvailable(self,fd, Args):
        print("lalalalalaalalalalalalalallaalalalalalala")
        fileToSend = Args[0]
        # fileToSend = open(")
        lftpSocket = Args[1]
        print(lftpSocket.__str__())


        data = fileToSend.read(800)

        print("datais:" + data)
        if data:
            vsFtpPacket = VsPacket()
            vsFtpPacket.type = VsPacket.TYPE_DATA
            vsFtpPacket.data = data
            if lftpSocket.sendToAll(vsFtpPacket.pack()) == False:
                print("Transmission error, quiting")
                sys.exit()
        else:
            ''' Send END packet'''
            vsFtpPacket = VsPacket()
            vsFtpPacket.type = VsPacket.TYPE_END
            vsFtpPacket.data = data
            if lftpSocket.sendToAll(vsFtpPacket.pack()) == False:
                print("Transmission error, quiting")
            Event.eventFdDelete(self.handleFileDataAvailable, (fileToSend, lftpSocket))
            Lftp.closeSocket(lftpSocket)



    def receiveHandler(self, lftpSocket, senderAddress, data):
        packet = VsPacket().unpack(data)
        print(">> " + str(packet))
        
        ''' Get or create file info object'''
        fileInfo = None
        for fInfoTmp in self.files:
            if fInfoTmp.sender == senderAddress:
                fileInfo = fInfoTmp
        if fileInfo is None:
            fileInfo = FileInfo()
            fileInfo.sender = senderAddress
            self.files.append(fileInfo)
        
        ''' Handle different VSFTP pacekt types'''
        if packet.type == VsPacket.TYPE_BEGIN:
            if fileInfo.filename is not None:
                print("File already open !!!!")
                sys.exit(1)
            
            filename = packet.data
            print("GOT PACKET BEGIN, openning fileToWrite for writing:" + filename)
            fileInfo.filename = filename
            fileInfo.filehandle = open(filename,'w')
            fileInfo.sendStarted = Event.getCurrentMills()  
            pass
        elif packet.type == VsPacket.TYPE_DATA:
            fileInfo.filehandle.write(packet.data)
            pass
        elif packet.type == VsPacket.TYPE_END:
            print("GOT PACKET END, closing file")
            fileInfo.filehandle.close()
            self.files.remove(fileInfo)
            print("Socket closed event received on " + str(lftpSocket))
            print("Lost Packets:" + str(lftpSocket.packetloss))
            print("Sent Data packets:" + str(lftpSocket.packetsSentData))
            print("Sent Control packets:" + str(lftpSocket.packetsSentControl))
            print("Received packets(total):" + str(lftpSocket.packetsReceived))
            print("Received data packets:" + str(lftpSocket.packetsReceivedData))
            print("Received and skipped packets:" + str(lftpSocket.packetsReceivedIgnored))
            print("Fake loss:" + str(lftpSocket.packetFakeLoss))
            print("Time taken: " + str((Event.getCurrentMills() - fileInfo.sendStarted)))
    
            pass  
        pass


class FileInfo:
    sender = None
    filename = None
    filehandle = None
    sendStarted = None

if __name__ == '__main__':
    Logging.Logger.setFile("receiver.log")  # Set file for log messages
    if len(sys.argv) < 2:
        print("Please provide port number, ex: python LftpReceiver.py 5000")
    else:
        Receiver("0.0.0.0", int(sys.argv[1])).start()
