# -*- coding: utf-8 -*-
import socket
import struct
import json
import Event
import sys
from random import randint
from Logging import Logger
from Logging import Level

lftpSockets = []
logger = Logger("LFTP", Level.TRACE)


def createSocket(addr, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((addr, port))
    lftpSocket = LftpSocket(sock)
    lftpSocket.addr_src = sock.getsockname()
    lftpSockets.append(lftpSocket)
    Event.eventFd(sock.fileno(), handleDataAvailable, lftpSocket, "DataReceived")
    return lftpSocket


def closeSocket(lftpSocket):
    ''' Called by user application '''
    for rs in lftpSockets:
        if rs == lftpSocket:
            logger.log(Level.INFO, "Closing socket:" + str(rs))
            rs.close()


def socketFinished(lftpSocket):
    ''' Called by child sockets when they finish'''
    Event.eventFdDelete(handleDataAvailable, lftpSocket)
    lftpSockets.remove(lftpSocket)
    # lftpSocket.eventHandler(lftpSocket, Event.TYPE_CLOSED)


def sendToAll(lftpSocket, data, address):
    if lftpSocket.closePending:
        return False
    lftpPacket = LftpPacket()
    lftpPacket.seqnum = 1
    lftpPacket.data = data
    lftpSocket.socket.sendto(lftpPacket.pack(), address)
    # TODO: register timeout
    pass


def registerReceiveHandler(lftpSocket, handler):
    lftpSocket.receiveHandler = handler
    pass


def registerEventHandler(lftpSocket, handler):
    lftpSocket.eventHandler = handler
    pass


def handleDataAvailable(fd, lftpSocket):
    # print "Received data on fd:" + str(fd)
    # TODO: read data from lftpSocket
    for rs in lftpSockets:
        if rs == lftpSocket:
            lftpSocket.receive()


class LftpSocket:
    ''' Socket session states'''
    STATE_CLOSED = 1
    STATE_LISTEN = 2
    STATE_INITING = 3
    STATE_ESTABLISHED = 4
    PARAM_MAX_DATA_LENGH = 1000
    PARAM_TIMEOUT = 500  # in milliseconds
    PARAM_WINDOWS_SIZE_MAX = 3
    PARAM_RETIRES_MAX = 50
    FAKE_LOSS = 0  # In scale 1-5, where 5 = 50% loss
    packetloss = 0
    packetsSentData = 0
    packetsSentControl = 0
    packetsReceived = 0
    packetsReceivedData = 0
    packetsReceivedIgnored = 0
    packetFakeLoss = 0

    def registerPacketLoss(self):
        self.packetloss = self.packetloss + 1

    def registerDataPacketSent(self):
        self.packetsSentData = self.packetsSentData + 1

    def registerControlPacketSent(self):
        self.packetsSentControl = self.packetsSentControl + 1

    def registerPacketReceived(self):
        self.packetsReceived = self.packetsReceived + 1

    def registerPacketReceivedData(self):
        self.packetsReceivedData = self.packetsReceivedData + 1

    def registerPacketReceivedIgnored(self):
        self.packetsReceivedIgnored = self.packetsReceivedIgnored + 1

    def registerFakeLoss(self):
        self.packetFakeLoss = self.packetFakeLoss + 1

    def __init__(self, socket):
        self.socket = socket
        self.receiveHandler = None
        self.eventHandler = None
        self.peers = []  # List of peers that we initiated connections to
        self.senders = []  # List of peers that initiated connection towards us
        self.addr_src = None
        self.closePending = False
        self.closed = False

    def __str__(self):  # Override string representation
        return "LFTP socket:" + str(self.__dict__)

    def __eq__(self, other):
        return self.socket.fileno() == other.socket.fileno()

    def close(self):
        ''' Called by LFTP container instructing to close this LFTP socket'''
        self.closePending = True
        ''' Order close all sending peer sessions'''
        for peer in self.peers:
            if peer.finished is not True:
                peer.close()

    def _peerFinished(self):
        ''' Called by sending peer after receiving ACK for FIN'''
        allfinished = True
        for peer in self.peers:
            allfinished = allfinished & peer.finished
        if allfinished is True:
            logger.log(Level.INFO, "All peers finished for socket:" + str(self))
            self.close = True
            socketFinished(self)

        # 假如false呢？可能所有peers没有都finish

    def sendToAll(self, data):
        ''' Send data to all peers '''
        result = True
        for peer in self.peers:
            result & peer.sendToAll(data)
        return result

    def addPeer(self, address):
        peer = LftpSocketPeer(address)
        peer.lftpSocket = self
        self.peers.append(peer)
        return peer

    # 增加检验
    def sendPacketControl(self, address, lftpPacket):
        if self.closed:
            logger.log(Level.ERROR, "Tried to send on a close socket")
            return False
        self.socket.sendto(lftpPacket.pack(), address)
        logger.log(Level.TRACE, "")
        logger.log(Level.TRACE, ">>" + str(address) + str(lftpPacket))
        self.registerControlPacketSent()
        return True

    def sendPacketData(self, address, lftpPacket):
        if self.closed:
            logger.log(Level.ERROR, "Tried to send on a close socket")
            return False
        self.socket.sendto(lftpPacket.pack(), address)
        logger.log(Level.TRACE, "")
        logger.log(Level.TRACE, ">>" + str(lftpPacket))
        self.registerDataPacketSent()
        return True

    def findOrCreateSenderPeer(self, address, createNew):
        for sender in self.senders:
            if sender.addr == address:
                return sender
        ''' Create new sender '''
        if createNew:
            sender = LftpSocketPeer(address)
            self.senders.append(sender)
            return sender
        return None

    def _cleanUpSender(self, sender):
        self.senders.remove(sender)

    def receive(self):
        # print "Reading from lftpSocket"
        self.registerPacketReceived()
        data, addr = self.socket.recvfrom(1024)  # set buffer size
        lftpPacket = LftpPacket().unpack(data)
        logger.log(Level.TRACE, "")
        logger.log(Level.TRACE, "<<" + str(lftpPacket))

        ''' Simulate packet loss '''
        if self.FAKE_LOSS > 0 and randint(1, 10 / self.FAKE_LOSS) == 1:
            self.registerFakeLoss()
            logger.log(Level.DEBUG, "LOOSING PACKET!!!!!!!!!!!!!!")
            logger.log(Level.DEBUG, "LOOSING PACKET!!!!!!!!!!!!!!")
            logger.log(Level.DEBUG, "LOOSING PACKET!!!!!!!!!!!!!!")
            return

        ''' Find sender or '''
        sender = self.findOrCreateSenderPeer(addr, True)

        if lftpPacket.type == LftpPacket.TYPE_SYN:
            ''' Receiving side only'''

            if sender.state == LftpSocket.STATE_LISTEN:
                logger.log(Level.DEBUG, "Got SYN, sending ACK to " + str(addr) + " " + str(self))
                packet = LftpPacket()
                packet.type = LftpPacket.TYPE_ACK
                packet.seqnum = lftpPacket.seqnum + 1
                self.sendPacketControl(addr, packet)
                sender.state = LftpSocket.STATE_ESTABLISHED
            else:
                logger.log(Level.ERROR, "Received unexpected packet " + str(self))
                ''' This might happen if sender didn't receive our ACK, so we can simply resend ACK,'''
                ''' But only if no DATA packets have been received'''
                if (sender.nextReceivingSequenceNumber == 0):
                    packet = LftpPacket()
                    packet.type = LftpPacket.TYPE_ACK
                    packet.seqnum = lftpPacket.seqnum + 1
                    self.sendPacketControl(addr, packet)
                self.registerPacketReceivedIgnored()

        elif lftpPacket.type == LftpPacket.TYPE_DATA:
            self.registerPacketReceivedData()
            ''' Receiving side only'''
            if sender.state == LftpSocket.STATE_ESTABLISHED:
                logger.log(Level.DEBUG, str(self) + " received DATA")
                if sender.nextReceivingSequenceNumber != lftpPacket.seqnum:
                    logger.log(Level.ERROR,
                               "Packets out of order, was expecting:" + str(sender.nextReceivingSequenceNumber))
                    if lftpPacket.seqnum <= sender.nextReceivingSequenceNumber:
                        ''' We already got this packet, so we simply ACK it '''
                        logger.log(Level.INFO, "Duplicated packet, sending ACK")
                        packet = LftpPacket()
                        packet.seqnum = lftpPacket.seqnum + 1
                        packet.type = LftpPacket.TYPE_ACK
                        self.sendPacketControl(addr, packet)
                        self.registerPacketReceivedIgnored()
                    return

                self.receiveHandler(self, addr, lftpPacket.data)
                sender.nextReceivingSequenceNumber = lftpPacket.seqnum + 1
                packet = LftpPacket()
                packet.seqnum = sender.nextReceivingSequenceNumber
                packet.type = LftpPacket.TYPE_ACK
                self.sendPacketControl(addr, packet)
            else:
                logger.log(Level.ERROR, "ERROR session not ESTAB " + str(self) + " " + str(lftpPacket))
                self.registerPacketReceivedIgnored()

        elif lftpPacket.type == LftpPacket.TYPE_ACK:
            for peer in self.peers:
                if peer.addr == addr:
                    peer.handleACK(lftpPacket)
            pass

        elif lftpPacket.type == LftpPacket.TYPE_FIN:
            if sender.state == LftpSocket.STATE_ESTABLISHED or sender.state == LftpSocket.STATE_CLOSED:
                if lftpPacket.seqnum == sender.nextReceivingSequenceNumber:
                    logger.log(Level.DEBUG, "Received FIN, sending ACK and closing socket")
                    packet = LftpPacket()
                    packet.seqnum = sender.nextReceivingSequenceNumber + 1
                    packet.type = LftpPacket.TYPE_ACK
                    self.sendPacketControl(addr, packet)
                    sender.finished = True
                    sender.state = LftpSocket.STATE_CLOSED
                else:
                    logger.log(Level.ERROR, "FIN packet wrong seq")
                    self.registerPacketReceivedIgnored()
            else:
                logger.log(Level.ERROR, "Received FIN while not in STATE_ESTABLISHED")
                self.registerPacketReceivedIgnored()
            pass
        pass

    def generateSynPacket(self):
        packet = LftpPacket()
        packet.type = LftpPacket.TYPE_SYN
        packet.seqnum = randint(100, 100000)
        return packet


class LftpSocketPeer:
    ''' Class for holding related socket information for each of the peers'''

    def __init__(self, address):
        self.nextReceivingSequenceNumber = 0  # Next sequence number of packet to add to buffer
        self.nextBufferPacketSeqNumber = 0  # Next sequence number to user when putting packets into buffer
        self.nextSendingPacketSeqNumber = 0  # Next sequence number of packet when sending from buffer
        self.nextAckSeqNumber = 1  # Next expected sequence number of an ACK
        self.addr = address
        self.state = LftpSocket.STATE_LISTEN  # Should be socket scope only
        self.window = 3
        self.retries = 0
        self.dataBuffer = []
        self.lftpSocket = None
        self.finished = False
        self.closePending = False

    def __str__(self):
        return "Peer " + str(self.addr) + " state:" + str(self.state) + " src:" + str(self.lftpSocket.addr_src)

    def sendToAll(self, data):  # 三次握手
        if self.state == LftpSocket.STATE_LISTEN:
            print(str(self) + " not ESTABLISHED, sending SYN")
            packet = self.lftpSocket.generateSynPacket()
            self.nextAckSeqNumber = packet.seqnum + 1
            self.lftpSocket.sendPacketControl(self.addr, packet)
            self.state = LftpSocket.STATE_INITING
            Event.eventTimeout(LftpSocket.PARAM_TIMEOUT, self.__handleTimeoutSYN, packet.seqnum, "SYN timeout")
        elif self.state == LftpSocket.STATE_INITING:
            logger.log(Level.DEBUG, str(self) + " STATE_INITING, adding data to buffer")
        elif self.state == LftpSocket.STATE_ESTABLISHED:
            logger.log(Level.DEBUG, str(self) + " STATE_ESTABLISHED, adding data to buffer")
        elif self.state == LftpSocket.STATE_CLOSED:
            logger.log(Level.ERROR, str(self) + " STATE_CLOSED, adding data to buffer")
            return False
        # Build packet and add to buffer
        packet = LftpPacket()
        packet.type = LftpPacket.TYPE_DATA
        packet.data = data
        packet.seqnum = self.nextBufferPacketSeqNumber
        self.dataBuffer.append(packet)
        self.nextBufferPacketSeqNumber = self.nextBufferPacketSeqNumber + 1
        logger.log(Level.TRACE, "Buffer has packets:" + str(len(self.dataBuffer)))
        return True

    def __handleTimeoutSYN(self, packetSequenceNumber):
        logger.log(Level.DEBUG, "Handling SYN timeout of:" + str(packetSequenceNumber))
        Event.eventTimeoutDelete(self.__handleTimeoutSYN, packetSequenceNumber)
        if self.__incrementRetries():
            packet = self.lftpSocket.generateSynPacket()
            self.nextAckSeqNumber = packet.seqnum + 1
            logger.log(Level.INFO, "Retransmitting SYN")
            self.lftpSocket.sendPacketControl(self.addr, packet)
            Event.eventTimeout(LftpSocket.PARAM_TIMEOUT, self.__handleTimeoutSYN, packet.seqnum, "SYN timeout")

    def __handleTimeoutFIN(self, packetSequenceNumber):
        logger.log(Level.DEBUG, "Handling FIN timeout of:" + str(packetSequenceNumber))
        if self.__incrementRetries():
            Event.eventTimeoutDelete(self.__handleTimeoutFIN, packetSequenceNumber)
            packet = LftpPacket()
            packet.type = LftpPacket.TYPE_FIN
            packet.seqnum = packetSequenceNumber
            self.lftpSocket.sendPacketControl(self.addr, packet)
            Event.eventTimeout(LftpSocket.PARAM_TIMEOUT, self.__handleTimeoutFIN, packet.seqnum, "DATA Timeout")

    def __handleTimeoutData(self, lftpSecNum):
        logger.log(Level.DEBUG, "Handling packet timeout DATA packet seq:" + str(lftpSecNum))
        ''' Here we need to remove all other DATA packet timeouts'''
        for seq in range(lftpSecNum, self.nextSendingPacketSeqNumber):
            Event.eventTimeoutDelete(self.__handleTimeoutData, seq)
        if self.__incrementRetries():  # 若返回false，表示超过最大retry次数；否则可以进行retry
            ''' Decrease window size, reset packet index to the one we lost'''
            self.window = 1 if self.window - 1 < 1 else self.window - 1
            # 丢包表示buffer满了，应该减小window
            self.nextSendingPacketSeqNumber = lftpSecNum
            # 下一个送的就是丢失的
            self.__emptyBuffer()
            self.retries = self.retries + 1
            # 怎么又加1？？？_incrementRetries()里面不是加过了吗

    def close(self):
        ''' Order to close the socket'''
        self.closePending = True
        self.__checkClose()

    def __checkClose(self):
        ''' Send FIN if all packet have been sent - last packet in a buffer was sent and all have been ACK'ed'''
        if self.closePending is True:  # closepending 用来检测是否可以关闭服务器，尽在LftpSocketPeer出现
            logger.log(Level.DEBUG, str(self.nextBufferPacketSeqNumber) + " > " + str(self.nextSendingPacketSeqNumber) +
                       " > " + str(self.nextAckSeqNumber))
            if self.nextBufferPacketSeqNumber == self.nextSendingPacketSeqNumber == (self.nextAckSeqNumber - 1):
                logger.log(Level.DEBUG, "Closing peer socket:" + str(self))
                # 发送结束通知包，并开启等待回复的时间检测事件
                packet = LftpPacket()
                packet.type = LftpPacket.TYPE_FIN
                packet.seqnum = self.dataBuffer[self.nextSendingPacketSeqNumber - 1].seqnum + 1
                self.lftpSocket.sendPacketControl(self.addr, packet)
                Event.eventTimeout(LftpSocket.PARAM_TIMEOUT, self.__handleTimeoutFIN, packet.seqnum, "DATA Timeout")
                self.state = LftpSocket.STATE_CLOSED
            else:
                logger.log(Level.DEBUG, "Could not close peer socket yet !!!!")

    def handleACK(self, ackPacket):
        if ackPacket.seqnum != self.nextAckSeqNumber:  # nextAckSN 应该是下一个期望收到的ACK包
            logger.log(Level.ERROR, "ACK with wrong sequence number, probably arrived too late, ignoring")
            return

        # 处在INITING状态，接收到ACK后表示建立连接，
        if self.state == LftpSocket.STATE_INITING:
            ''' Must be ACK in response to SYN'''
            logger.log(Level.DEBUG, "Handling ACK for SYN")

            self.state = LftpSocket.STATE_ESTABLISHED
            self.nextAckSeqNumber = 1  # 连接已经建立，重置期待收到的ACK包序号，接下来就要传数据
            Event.eventTimeoutDelete(self.__handleTimeoutSYN, ackPacket.seqnum - 1)  # 删除从上一个包到达时设立的时间检测事件？
            self.__emptyBuffer()
            self.__resetRetries()

        # 处在连接已建立的状态，因此需要传送数据
        elif self.state == LftpSocket.STATE_ESTABLISHED:
            ''' Must be ACK in response to DATA'''
            logger.log(Level.DEBUG, "Handling ACK for DATA")
            logger.log(Level.DEBUG, "ACK CORRECT")
            Event.eventTimeoutDelete(self.__handleTimeoutData, ackPacket.seqnum - 1)
            self.nextAckSeqNumber = ackPacket.seqnum + 1
            self.window = self.window + 1
            self.__emptyBuffer()  # 将buffer中数据发送出去
            self.__resetRetries()  # 无丢失，重置retry
            self.__checkClose()  # 检测是否发完了  closepending

        # 处在close状态，因此收到ACK表示同意关闭，并且将原来注册的时间事件删除
        elif self.state == LftpSocket.STATE_CLOSED:
            ''' This must be the final ACK'''
            logger.log(Level.DEBUG, "Final ACK received:" + str(self.lftpSocket))
            # 对应于__checkClose() 函数
            Event.eventTimeoutDelete(self.__handleTimeoutFIN, ackPacket.seqnum - 1)
            self.finished = True
            self.lftpSocket._peerFinished()

    # 继续发完buffer中需要发的，window持续减少？
    def __emptyBuffer(self):
        logger.log(Level.TRACE,
                   "Sending packets, window:" + str(self.window) + " index:" + str(self.nextSendingPacketSeqNumber))
        if len(self.dataBuffer) > self.nextSendingPacketSeqNumber:
            while self.window > 0 and len(self.dataBuffer) > 0 and len(
                    self.dataBuffer) > self.nextSendingPacketSeqNumber:
                packet = self.dataBuffer[self.nextSendingPacketSeqNumber]
                self.lftpSocket.sendPacketData(self.addr, packet)
                self.nextSendingPacketSeqNumber = self.nextSendingPacketSeqNumber + 1
                self.window = self.window - 1
                Event.eventTimeout(LftpSocket.PARAM_TIMEOUT, self.__handleTimeoutData, packet.seqnum, "DATA Timeout")

    # 验证是否达到最大尝试次数，递增retries并注册丢包事件
    def __incrementRetries(self):
        self.retries = self.retries + 1
        self.lftpSocket.registerPacketLoss()
        if self.retries > LftpSocket.PARAM_RETIRES_MAX:
            logger.log(Level.ERROR, "Maximum number of " + str(LftpSocket.PARAM_RETIRES_MAX) + " retries reached")
            self.lftpSocket.eventHandler(self.lftpSocket, Event.TYPE_TIMEOUT)
            self.finished = True
            self.lftpSocket.close()
            return False
        return True

    def __resetRetries(self):
        self.retries = 0


class LftpPacket:
    """ LFTP packet class"""
    TYPE_DATA = 1
    TYPE_SYN = 2
    TYPE_ACK = 4
    TYPE_FIN = 5

    def __init__(self):
        self.version = 1
        self.type = None
        self.seqnum = 0
        self.datalength = None
        self.data = None

    def pack(self):
        # data = bytes(self.data)
        if self.data is None:
            self.datalength = 0
            data = bytes(0)
        else:
            data = bytes(self.data)
            self.datalength = len(data)
        return struct.pack("IIII%ds" % (len(data),), self.version, self.type, self.seqnum, self.datalength, data)

    def unpack(self, data):
        self.version, self.type, self.seqnum, self.datalength = struct.unpack("IIII", data[:16])
        if self.datalength > 0:
            (self.data,) = struct.unpack("%ds" % (self.datalength,), data[16:])
        return self

    def __str__(self):  # Override string representation
        return "LftpPacket " + str(self.__dict__)