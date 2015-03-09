
from ALU import ALU

regOffset = [ 'B', 'C', 'D', 'E', 'H', 'L', 'M', 'A' ]
regPair = { 'H':'L', 'B':'C', 'D':'E', 'A':'F' }

mvi_map = { 0x3E:'A', 0x06:'B', 0x0E:'C', 0x16:'D', 0x1E:'E', 0x26:'H', 0x2E:'L', 0x36:'M' }
lxi_map = { 0x01:'B', 0x11:'D', 0x21:'H', 0x31:'SP' }
push_map = { 0xC5:'B', 0xD5:'D', 0xE5:'H', 0xF5:'A' }
pop_map = { 0xC1:'B', 0xD1:'D', 0xE1:'H', 0xF1:'A' }
mov_map = { 0x78:'A', 0x40:'B', 0x48:'C', 0x50:'D', 0x58:'E', 0x60:'H', 0x68:'L', 0x70:'M' }
rst_map = [ 0xC7, 0xCF, 0xD7, 0xDF, 0xE7, 0xEF, 0xF7, 0xFF ]

aux_word = 0
def CheckOffset(byte, base):
    global aux_word
    diff = byte - base
    if diff >= 0 and diff < 8:
        aux_word = base
        return True
    return False

def CheckMov(byte):
    for i in mov_map:
        if CheckOffset(byte, i):
            return True
    return False


class CU:
    def __init__(self, alu, bus):
        self.alu = alu
        self.bus = bus

    def Reset(self):
        self.running = False
        self.opcode = 0x0
        self.intMasks = 0x07
        self.intEnable = False

        self.interrupter = None
        self.interrupt = -1

        self.bus.WriteMemory(0x0028, 0x76)
    
    def GetPC(self):
        return self.alu.registers['PC']

    def SetPC(self, addr):
        self.alu.registers['PC'] = addr

    def TRAP(self):
        self.Rst(0x0024)

    def RST(self, n, interrupter):
        i = int(n-5.5)
        if self.intMasks & (0x1 << i) == (0x1 << i):
            return
        self.interrupter = interrupter
        self.interrupt = i
        
    def Run(self):
        self.running = True
        while self.running:
            self.SingleStep()
    
    def Fetch(self):
        pc = self.GetPC()
        self.SetPC(pc+1)
        byte = self.bus.ReadMemory(pc)
        if byte > 0xFF:
            raise Exception("Invalid byte at " + hex(pc) + " : " + str(byte))
        return byte

    def ProcessInterrupts(self):
        if not self.intEnable:
            return
        if self.interrupt == -1:
            return
        self.Di()
        if not self.interrupter is None:
            self.interrupter.Inta()
            self.interrupter = None
        self.Rst(self.interrupt*8+0x002C)
        self.interrupt = -1

    
    def GetData(self, reg):
        if reg == 'M':
            return self.bus.ReadMemory(self.alu.GetHL())
        return self.alu.registers[reg]

    def SetData(self, reg, data):
        if reg == 'M':
            self.bus.WriteMemory(self.alu.GetHL(), data)
        else:
            self.alu.registers[reg] = data

    def Mvi(self):
        reg = mvi_map[self.opcode]
        byte = self.Fetch()
        self.SetData(reg, byte)

    def Lxi(self):
        byteL = self.Fetch()
        byteH = self.Fetch()
        
        regH = lxi_map[self.opcode]
        if regH == 'SP':
            self.SetData(regH, (byteH << 8) | byteL)
        else:
            regL = regPair[regH]
            self.SetData(regH, byteH)
            self.SetData(regL, byteL)

    def Mov(self):
        dreg = mov_map[aux_word]
        sreg = regOffset[self.opcode-aux_word]
        self.SetData(dreg, self.GetData(sreg))
        

    def Adi(self, carry=False):
        byte = self.Fetch()
        self.alu.Add(byte, carry)

    def Add(self, carry=False):
        sreg = regOffset[self.opcode-aux_word]
        self.alu.Add(self.GetData(sreg), carry)

    def Sbi(self, burrow=False):
        byte = self.Fetch()
        self.alu.Sub(byte, burrow)

    def Sub(self, burrow=False):
        sreg = regOffset[self.opcode-aux_word]
        self.alu.Add(self.GetData(sreg), burrow)

    def Ani(self):
        byte = self.Fetch()
        self.alu.And(byte)

    def Ana(self):
        sreg = regOffset[self.opcode-aux_word]
        self.alu.And(self.GetData(sreg))

    def Xri(self):
        byte = self.Fetch()
        self.alu.Xor(byte)

    def Xra(self):
        sreg = regOffset[self.opcode-aux_word]
        self.alu.Xor(self.GetData(sreg))

    def Ori(self):
        byte = self.Fetch()
        self.alu.Or(byte)

    def Ora(self):
        sreg = regOffset[self.opcode-aux_word]
        self.alu.Or(self.GetData(sreg))

    def Out(self):
        byte = self.Fetch()
        self.bus.WriteIO(byte, self.alu.registers['A'])

    def In(self):
        byte = self.Fetch()
        self.alu.registers['A'] = self.bus.ReadIO(byte)

    def PushBytes(self, hByte, lByte):
        self.alu.registers['SP'] -= 1
        self.bus.WriteMemory(self.alu.registers['SP'], hByte)
        self.alu.registers['SP'] -= 1
        self.bus.WriteMemory(self.alu.registers['SP'], lByte)

    def PopBytes(self):
        low = self.bus.ReadMemory(self.alu.registers['SP'])
        self.alu.registers['SP'] += 1
        high = self.bus.ReadMemory(self.alu.registers['SP'])
        self.alu.registers['SP'] += 1
        return high, low

    def Push(self):
        regH = push_map[self.opcode]
        regL = regPair[regH]
        self.PushBytes(self.alu.registers[regH], self.alu.registers[regL])

    def Pop(self):
        regH = pop_map[self.opcode]
        regL = regPair[regH]
        high, low = self.PopBytes()
        self.alu.registers[regL] = low
        self.alu.registers[regH] = high

    def Sim(self):
        acc = self.alu.registers['A']
        if acc & 0x08 == 0x08:
            self.intMasks = (self.intMasks & 0xF8) | (acc & 0x07)

    def Ei(self):
        self.intEnable = True

    def Di(self):
        self.intEnable = False

    def Rst(self, addr):
        self.PushBytes((self.GetPC() & 0xFF00) >> 8, self.GetPC() & 0x00FF)
        self.SetPC(addr)

    def Ret(self):
        high, low = self.PopBytes()
        self.SetPC((high << 8) | low)
    
    def Jmp(self):
        adL = self.Fetch()
        adH = self.Fetch()
        addr = (adH << 8) | adL
        self.SetPC(addr)
            
    def SingleStep(self):
        self.FetchAndDecode()
        self.ProcessInterrupts()

    def FetchAndDecode(self):
        byte = self.Fetch()
        self.opcode = byte
        if byte == 0x00:
            pass
        elif byte == 0x76:
            self.running = False
        elif byte in mvi_map:
            self.Mvi()
        elif byte in lxi_map:
            self.Lxi()
        elif byte in push_map:
            self.Push()
        elif byte in pop_map:
            self.Pop()
        elif CheckMov(byte):
            self.Mov()
        elif byte == 0xC6:
            self.Adi()
        elif byte == 0xCE:
            self.Adi(True)
        elif CheckOffset(byte, 0x80):
            self.Add()
        elif CheckOffset(byte, 0x88):
            self.Add(True)
        elif byte == 0xD6:
            self.Sbi()
        elif byte == 0xDE:
            self.Sbi(True)
        elif CheckOffset(byte, 0x90):
            self.Sub()
        elif CheckOffset(byte, 0x98):
            self.Sub(True)
        elif byte == 0xE6:
            self.Ani()
        elif CheckOffset(byte, 0xA0):
            self.Ana()
        elif byte == 0xF6:
            self.Ori()
        elif CheckOffset(byte, 0xB3):
            self.Ora()
        elif byte == 0xEE:
            self.Xri()
        elif CheckOffset(byte, 0xA8):
            self.Xra()
        elif byte == 0xDB:
            self.In()
        elif byte == 0xD3:
            self.Out()
        elif byte == 0xF3:
            self.Di()
        elif byte == 0xFB:
            self.Ei()
        elif byte == 0x30:
            self.Sim()
        elif byte == 0xC9:
            self.Ret()
        elif byte == 0xC3:
            self.Jmp()
        elif byte in rst_map:
            self.Rst(rst_map.index(byte) * 8)
        else:
            raise Exception("Invalid opcode: " + hex(byte))

