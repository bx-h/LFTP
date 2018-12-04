'''
Created on May 12, 2013

@author: Saulius Alisauskas
'''

import struct

class VsPacket:
    TYPE_BEGIN = 1
    TYPE_DATA = 2
    TYPE_END = 3
    RT_PUT = 1
    RT_GET = 2
    
    def __init__(self):
        self.type = None
        self.data = ""
        self.Rt = 0
      
    def pack(self):
        data = bytes(self.data)
        if self.data is None:
            self.datalength = 0
        else:
            self.datalength = len(data)
        return struct.pack("II%ds" % (self.datalength,), self.type, self.Rt, data)

    def unpack(self, data):
        self.type, self.Rt = struct.unpack("II", data[:8])
        if self.type == self.TYPE_BEGIN or self.type == self.TYPE_DATA:
            (self.data,) = struct.unpack("%ds" % (len(data) - 8), data[8:])
        return self
    
    def __str__(self): # Override string representation
        return "VsPacket type:" + str(self.type) + " datasize:" + str(len(self.data))
