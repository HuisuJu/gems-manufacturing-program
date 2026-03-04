from logger import Logger, LogLevel
import serial
import serial.tools.list_ports
import serial.threaded
from cobs import cobs
from blinker import Signal
from queue import Queue

class SerialConnection(serial.threaded.Packetizer):
    TERMINATOR = b'\x00'

    def __init__(self, event: Signal, read_queue: Queue):
        super().__init__()
        self.event = event
        self.read_queue = read_queue

    def connection_made(self, transport):
        super().connection_made(transport)
        self.event.send(self, event='connected')
        Logger.write(LogLevel.PROGRESS, "Serial port is connected!!")

    def connection_lost(self, exc):
        self.event.send(self, event='disconnected')
        Logger.write(LogLevel.PROGRESS, "Serial port is disconnected!!")
        super().connection_lost(exc)

    def handle_packet(self, packet):
        if not packet:
            return
        try:
            msg = cobs.decode(packet)
            self.read_queue.put(msg)
        except Exception as e:
            print('TODO')

class SerialManager:
    TIMEOUT = 3
    event = Signal()

    def __init__(self):
        self.serial = None
        self.thread = None
        self.queue = Queue()

    @staticmethod
    def list_ports() -> list[str]:
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]

    def is_connected(self) -> bool:
        return self.serial is not None and self.serial.is_open

    def open(self, port, baudrate=115200) -> bool:
        if self.is_connected():
            self.close()
        try:
            self.serial = serial.Serial(port, baudrate, timeout=0.2)
            self.thread = serial.threaded.ReaderThread(
                self.serial, lambda: SerialConnection(self.event, self.queue)
            )
            self.thread.start()
            return True
        except Exception as e:
            print('TODO')
            self.close()
            return False

    def close(self):
        try:
            if self.thread:
                self.thread.stop()
        finally:
            self.thread = None
            if self.serial and self.serial.is_open:
                self.serial.close()
            self.serial = None

    def read(self) -> bytes | None:
        try:
            return self.queue.get(timeout=self.TIMEOUT)
        except Exception as e:
            return None

    def write(self, buf: bytes) -> bool:
        if not (self.thread and self.serial and self.serial.is_open):
            return False
        try:
            self.thread.write(cobs.encode(buf) + b'\x00')
            return True
        except Exception as e:
            print('TODO')
            return False
        
serial_manager = SerialManager()
