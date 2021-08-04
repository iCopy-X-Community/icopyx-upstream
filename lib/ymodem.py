import os
import time
import math

import hmi_driver
import update

SOH = b'\x01'
STX = b'\x02'
EOT = b'\x04'
ACK = b'\x06'
NAK = b'\x15'
CAN = b'\x18'
CRC = b'C'


def bytesToHexString(bs):
    # hex_str = ''
    # for item in bs:
    #     hex_str += str(hex(item))[2:].zfill(2).upper() + " "
    # return hex_str
    if isinstance(bs, int): return '%02X'.format(bs)
    return ''.join(['%02X' % b for b in bs])


class YModemSTM32:

    # initialize
    def __init__(self, getc, putc, mode='ymodem', header_pad=b'\x00', pad=b'\x1a'):
        self.getc = getc
        self.putc = putc
        self.mode = mode
        self.header_pad = header_pad
        self.pad = pad

    # send abort(CAN) twice
    def abort(self, count=2):
        for _ in range(count):
            self.putc(CAN)

    '''
    send entry
    '''

    def send(self, file_stream, file_name, file_size, retry=20, callback=None):
        try:
            packet_size = dict(
                ymodem=1024,
                ymodem128=128
            )[self.mode]
        except KeyError:
            raise ValueError("Invalid mode specified: {self.mode!r}".format(self=self))

        print('Begin start sequence')

        # Receive first character
        error_count = 0
        cancel = 0
        while True:
            char = self.getc(1)
            if char:
                if char == CRC:
                    # Expected CRC
                    print("<<< CRC1")
                    break
                elif char == CAN:
                    print("<<< CAN1")
                    if cancel:
                        return False
                    else:
                        cancel = 1
                else:
                    print("send error, expected CRC or CAN, but got " + hex(ord(char)))

            error_count += 1
            if error_count > retry:
                self.abort()
                print("send error: error_count reached %d aborting", retry)
                return False

        header = self._make_send_header(128, 0)
        name = bytes(file_name, encoding="utf8")

        size = bytes(str(file_size), encoding="utf8")

        data = name + b'\x00' + size + b'\x20'

        data = data.ljust(128, self.header_pad)

        checksum = self._make_send_checksum(data)
        data_for_send = header + data + checksum
        self.putc(data_for_send)

        print(f"Packet name: {name}")
        print(f"Packet size: {size}")
        print(f"Packet data: {data_for_send}")

        print("Packet 0 >>> " + str(len(data_for_send)))

        cancel = 0
        # Receive reponse of first packet
        while True:
            char = self.getc(1)
            if char:
                if char == ACK:
                    print("<<< ACK1")
                    char2 = self.getc(1)
                    if char2 == CRC:
                        print("<<< CRC")
                        break
                    else:
                        print("ACK wasnt CRCd")
                        break
                elif char == CAN:
                    print("<<< CAN")
                    if cancel:
                        return False
                    else:
                        cancel = 1
                else:
                    if 0x20 <= (ord(char)) <= 0x7e:
                        print("test" + str(char))
                    else:
                        print("send error, expected ACK or CAN, but got " + hex(ord(char)))

        total_packets = 1
        total_size = 0
        sequence = 1

        print("Packet 1 + start >>>")

        time.sleep(1)

        while True:
            # Read raw data from file stream
            data = file_stream.read(packet_size)
            if not data:
                print('send: at EOF')
                break
            total_packets += 1
            total_size += len(data)

            header = self._make_send_header(packet_size, sequence)
            data = data.ljust(packet_size, self.pad)
            checksum = self._make_send_checksum(data)

            while True:
                data_for_send = header + data + checksum
                # data_in_hexstring = "".join("%02x" % b for b in data_for_send)

                self.putc(data_for_send)

                print("Packet " + str(sequence) + " >>> " + str(len(data_for_send)))
                error_count = 0

                while True:
                    char = self.getc(1)
                    print(f"self.getc(1) == {char} with retry == {retry}")

                    if char == ACK:
                        break
                    else:
                        error_count += 1

                    if error_count > retry:
                        self.abort()
                        print("self.abort()")
                        return False

                error_count = 0
                if char == ACK:
                    # Expected response
                    print("<<< ACK2")
                    if callable(callback):
                        callback(total_size, file_size, file_name)
                    break

                error_count += 1

                if error_count > retry:
                    self.abort()
                    print('send error: NAK received %d , aborting', retry)
                    return False

            sequence = (sequence + 1) % 0x100

        print("Wait ok >>>")

        # Send EOT and expect final ACK
        error_count = 0
        while True:
            self.putc(EOT)
            print(">>> EOT")
            char = self.getc(1)
            if char == ACK:
                print("<<< ACK3")
                break
            else:
                error_count += 1
                if error_count > retry:
                    self.abort()
                    print('EOT wasnt ACKd, aborting transfer')
                    return False

        header = self._make_send_header(128, 0)

        data = bytearray(b'\x00')

        data = data.ljust(128, self.header_pad)

        checksum = self._make_send_checksum(data)
        data_for_send = header + data + checksum
        self.putc(data_for_send)

        error_count = 0
        while True:
            char = self.getc(1)
            if char == ACK:
                break
            else:
                error_count += 1
                if error_count > retry:
                    self.abort()
                    print('SOH wasnt ACK, aborting transfer')
                    return False

        print('Transmission successful (ACK received)')
        return True

    # Header byte
    def _make_send_header(self, packet_size, sequence):
        assert packet_size in (128, 1024), packet_size
        _bytes = []
        if packet_size == 128:
            _bytes.append(ord(SOH))
        elif packet_size == 1024:
            _bytes.append(ord(STX))
        _bytes.extend([sequence, 0xff - sequence])
        return bytearray(_bytes)

    # Make check code
    def _make_send_checksum(self, data):
        _bytes = []
        crc = self.calc_crc(data)
        _bytes.extend([crc >> 8, crc & 0xff])
        return bytearray(_bytes)

    def _verify_recv_checksum(self, data):
        _checksum = bytearray(data[-2:])
        their_sum = (_checksum[0] << 8) + _checksum[1]
        data = data[:-2]

        our_sum = self.calc_crc(data)
        valid = bool(their_sum == our_sum)
        return valid, data

    # For CRC algorithm
    crctable = [
        0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50a5, 0x60c6, 0x70e7,
        0x8108, 0x9129, 0xa14a, 0xb16b, 0xc18c, 0xd1ad, 0xe1ce, 0xf1ef,
        0x1231, 0x0210, 0x3273, 0x2252, 0x52b5, 0x4294, 0x72f7, 0x62d6,
        0x9339, 0x8318, 0xb37b, 0xa35a, 0xd3bd, 0xc39c, 0xf3ff, 0xe3de,
        0x2462, 0x3443, 0x0420, 0x1401, 0x64e6, 0x74c7, 0x44a4, 0x5485,
        0xa56a, 0xb54b, 0x8528, 0x9509, 0xe5ee, 0xf5cf, 0xc5ac, 0xd58d,
        0x3653, 0x2672, 0x1611, 0x0630, 0x76d7, 0x66f6, 0x5695, 0x46b4,
        0xb75b, 0xa77a, 0x9719, 0x8738, 0xf7df, 0xe7fe, 0xd79d, 0xc7bc,
        0x48c4, 0x58e5, 0x6886, 0x78a7, 0x0840, 0x1861, 0x2802, 0x3823,
        0xc9cc, 0xd9ed, 0xe98e, 0xf9af, 0x8948, 0x9969, 0xa90a, 0xb92b,
        0x5af5, 0x4ad4, 0x7ab7, 0x6a96, 0x1a71, 0x0a50, 0x3a33, 0x2a12,
        0xdbfd, 0xcbdc, 0xfbbf, 0xeb9e, 0x9b79, 0x8b58, 0xbb3b, 0xab1a,
        0x6ca6, 0x7c87, 0x4ce4, 0x5cc5, 0x2c22, 0x3c03, 0x0c60, 0x1c41,
        0xedae, 0xfd8f, 0xcdec, 0xddcd, 0xad2a, 0xbd0b, 0x8d68, 0x9d49,
        0x7e97, 0x6eb6, 0x5ed5, 0x4ef4, 0x3e13, 0x2e32, 0x1e51, 0x0e70,
        0xff9f, 0xefbe, 0xdfdd, 0xcffc, 0xbf1b, 0xaf3a, 0x9f59, 0x8f78,
        0x9188, 0x81a9, 0xb1ca, 0xa1eb, 0xd10c, 0xc12d, 0xf14e, 0xe16f,
        0x1080, 0x00a1, 0x30c2, 0x20e3, 0x5004, 0x4025, 0x7046, 0x6067,
        0x83b9, 0x9398, 0xa3fb, 0xb3da, 0xc33d, 0xd31c, 0xe37f, 0xf35e,
        0x02b1, 0x1290, 0x22f3, 0x32d2, 0x4235, 0x5214, 0x6277, 0x7256,
        0xb5ea, 0xa5cb, 0x95a8, 0x8589, 0xf56e, 0xe54f, 0xd52c, 0xc50d,
        0x34e2, 0x24c3, 0x14a0, 0x0481, 0x7466, 0x6447, 0x5424, 0x4405,
        0xa7db, 0xb7fa, 0x8799, 0x97b8, 0xe75f, 0xf77e, 0xc71d, 0xd73c,
        0x26d3, 0x36f2, 0x0691, 0x16b0, 0x6657, 0x7676, 0x4615, 0x5634,
        0xd94c, 0xc96d, 0xf90e, 0xe92f, 0x99c8, 0x89e9, 0xb98a, 0xa9ab,
        0x5844, 0x4865, 0x7806, 0x6827, 0x18c0, 0x08e1, 0x3882, 0x28a3,
        0xcb7d, 0xdb5c, 0xeb3f, 0xfb1e, 0x8bf9, 0x9bd8, 0xabbb, 0xbb9a,
        0x4a75, 0x5a54, 0x6a37, 0x7a16, 0x0af1, 0x1ad0, 0x2ab3, 0x3a92,
        0xfd2e, 0xed0f, 0xdd6c, 0xcd4d, 0xbdaa, 0xad8b, 0x9de8, 0x8dc9,
        0x7c26, 0x6c07, 0x5c64, 0x4c45, 0x3ca2, 0x2c83, 0x1ce0, 0x0cc1,
        0xef1f, 0xff3e, 0xcf5d, 0xdf7c, 0xaf9b, 0xbfba, 0x8fd9, 0x9ff8,
        0x6e17, 0x7e36, 0x4e55, 0x5e74, 0x2e93, 0x3eb2, 0x0ed1, 0x1ef0,
    ]

    # CRC algorithm: CCITT-0
    def calc_crc(self, data, crc=0):
        # print("将被计算CRC的数据: ", data)
        for char in bytearray(data):
            crctbl_idx = ((crc >> 8) ^ char) & 0xff
            crc = ((crc << 8) ^ self.crctable[crctbl_idx]) & 0xffff
        return crc & 0xffff


class YModemCommon:

    def __init__(self, getc, putc, header_pad=b'\x00', data_pad=b'\x1a'):
        self.getc = getc
        self.putc = putc
        self.st = SendTask()
        self.rt = ReceiveTask()
        self.header_pad = header_pad
        self.data_pad = data_pad

    def abort(self, count=2):
        for _ in range(count):
            self.putc(CAN)

    def send_file(self, file_path, retry=20, callback=None):
        file_stream = None
        try:
            file_stream = open(file_path, 'rb')
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            file_sent = self.send(file_stream, file_name, file_size, retry, callback)

            print("Task Done!")
            print("File: " + file_name)
            print("Size: " + str(file_sent) + "Bytes")
            print("Packets: " + str(self.st.get_valid_sent_packets()))

        except IOError as e:
            print(str(e))
            return False
        finally:
            if file_stream is not None:
                file_stream.close()
        return file_sent

    def wait_for_next(self, ch):
        cancel_count = 0
        while True:
            c = self.getc(1)
            if c:
                if c == ch:
                    print("<<< " + hex(ord(ch)))
                    break
                elif c == CAN:
                    if cancel_count == 2:
                        return -1
                    else:
                        cancel_count += 1
                else:
                    print("Expected " + hex(ord(ch)) + ", but got " + hex(ord(c)))
        return 0

    def send(self, data_stream, data_name, data_size, retry=20, callback=None):
        packet_size = 1024

        # [<<< CRC]
        self.wait_for_next(CRC)

        print("已经收到了CRC，开始接收第一帧的头部包")

        # [first packet >>>]
        header = self._make_edge_packet_header()

        if len(data_name) > 100:
            data_name = data_name[:100]
        self.st.set_task_name(data_name)
        data_name += bytes.decode(self.header_pad)

        data_size = str(data_size)
        if len(data_size) > 20:
            raise Exception("Data volume is too large!")
        self.st.set_task_size(int(data_size))
        data_size += bytes.decode(self.header_pad)

        data = data_name + data_size
        data = data.encode()
        data = data.ljust(128, self.header_pad)

        checksum = self._make_send_checksum(data)

        data_for_send = header + data + checksum

        print("最终生成的包头长度: ", len(header))
        print("最终生成的数据长度: ", len(data))
        print("最终生成的校验长度: ", len(checksum))
        print("最终生成的校验数据: ", "".join("%02x" % b for b in checksum))

        self.putc(data_for_send)
        self.st.inc_sent_packets()
        # data_in_hexstring = "".join("%02x" % b for b in data_for_send)
        print("Packet 0 >>>")

        # [<<< ACK]
        # [<<< CRC]
        self.wait_for_next(ACK)
        self.wait_for_next(CRC)

        # [data packet >>>]
        # [<<< ACK]
        error_count = 0
        sequence = 1
        while True:
            data = data_stream.read(packet_size)

            if not data:
                print('EOF')
                break

            extracted_data_bytes = len(data)

            if extracted_data_bytes <= 128:
                packet_size = 128

            header = self._make_data_packet_header(packet_size, sequence)
            data = data.ljust(packet_size, self.data_pad)
            checksum = self._make_send_checksum(data)
            data_for_send = header + data + checksum
            # data_in_hexstring = "".join("%02x" % b for b in data_for_send)

            while True:
                self.putc(data_for_send)
                self.st.inc_sent_packets()
                print("Packet " + str(sequence) + " >>>")

                c = self.getc(1)
                if c == ACK:
                    print("<<< ACK")
                    self.st.inc_valid_sent_packets()
                    self.st.add_valid_sent_bytes(extracted_data_bytes)
                    error_count = 0
                    break
                else:
                    error_count += 1
                    self.st.inc_missing_sent_packets()
                    print("RETRY " + str(error_count))

                    if error_count > retry:
                        self.abort()
                        print('send error: NAK received %d , aborting', retry)
                        return -2

            sequence = (sequence + 1) % 0x100

        # [EOT >>>]
        # [<<< NAK]
        # [EOT >>>]
        # [<<< ACK]
        self.putc(EOT)
        print(">>> EOT")
        self.wait_for_next(NAK)
        self.putc(EOT)
        print(">>> EOT")
        self.wait_for_next(ACK)

        # [<<< CRC]
        self.wait_for_next(CRC)

        # [Final packet >>>]
        header = self._make_edge_packet_header()
        data = "".ljust(128, bytes.decode(self.header_pad))
        checksum = self._make_send_checksum(data)
        data_for_send = header + data.encode() + checksum
        self.putc(data_for_send)
        self.st.inc_sent_packets()
        print("Packet End >>>")

        self.wait_for_next(ACK)

        return self.st.get_valid_sent_bytes()

    def wait_for_header(self):
        cancel_count = 0
        while True:
            c = self.getc(1)
            if c:
                if c == SOH or c == STX:
                    return c
                elif c == CAN:
                    if cancel_count == 2:
                        return -1
                    else:
                        cancel_count += 1
                else:
                    print(
                        "wait_for_header() -> Expected 0x01(SOH)/0x02(STX)/0x18(CAN), but got " + hex(ord(c))
                    )

    def wait_for_eot(self):
        eot_count = 0
        while True:
            c = self.getc(1)
            if c:
                if c == EOT:
                    eot_count += 1
                    if eot_count == 1:
                        print("EOT >>>")
                        self.putc(NAK)
                        print("<<< NAK")
                    elif eot_count == 2:
                        print("EOT >>>")
                        self.putc(ACK)
                        print("<<< ACK")
                        self.putc(CRC)
                        print("<<< CRC")
                        break
                else:
                    print("Expected 0x04(EOT), but got " + hex(ord(c)))

    def recv_file(self, root_path, callback=None):
        while True:
            self.putc(CRC)
            print("<<< CRC")
            c = self.getc(1)
            if c:
                if c == SOH:
                    packet_size = 128
                    break
                elif c == STX:
                    packet_size = 1024
                    break
                else:
                    print("recv_file() -> Expected 0x01(SOH)/0x02(STX)/0x18(CAN), but got " + hex(ord(c)))

        print("接收方收到了CRC，开始下一步...")

        IS_FIRST_PACKET = True
        FIRST_PACKET_RECEIVED = False
        WAIT_FOR_EOT = False
        WAIT_FOR_END_PACKET = False
        sequence = 0
        file_stream = None

        while True:
            if WAIT_FOR_EOT:
                self.wait_for_eot()
                WAIT_FOR_EOT = False
                WAIT_FOR_END_PACKET = True
                sequence = 0
            else:
                if IS_FIRST_PACKET:
                    IS_FIRST_PACKET = False
                else:
                    c = self.wait_for_header()

                    if c == SOH:
                        packet_size = 128
                    elif c == STX:
                        packet_size = 1024
                    else:
                        return c

                # print("在循环中开始接收数据...")

                seq = self.getc(1)
                seq_oc = None
                if seq is None:
                    seq_oc = None
                else:
                    seq = ord(seq)
                    c = self.getc(1)
                    if c is not None: seq_oc = 0xFF - ord(c)

                data = self.getc(packet_size + 2)

                # print("")
                # print("SEQ == ", seq)
                # print("SEQ_OC == ", seq_oc)
                # print("SEQUENCE == ", sequence)
                # print("")

                if not (seq == seq_oc == sequence):
                    continue
                else:
                    # print("开始校验CRC16...")
                    valid, _ = self._verify_recv_checksum(data)
                    # print(f"校验结果: {valid}")

                    if valid:
                        # first packet
                        # [<<< ACK]
                        # [<<< CRC]
                        if seq == 0 and not FIRST_PACKET_RECEIVED and not WAIT_FOR_END_PACKET:
                            print("Packet 0 >>>")
                            self.putc(ACK)
                            print("<<< ACK")
                            self.putc(CRC)
                            print("<<< CRC")
                            file_name_bytes, data_size_bytes = (data[:-2]).rstrip(self.header_pad).split(
                                self.header_pad)
                            file_name = bytes.decode(file_name_bytes)
                            data_size = bytes.decode(data_size_bytes)
                            print("TASK: " + file_name + " " + data_size + "Bytes")
                            self.rt.set_task_name(file_name)
                            self.rt.set_task_size(int(data_size))

                            # create dir if no exists...
                            if not os.path.exists(root_path):
                                os.makedirs(root_path)

                            file_final = os.path.join(root_path, file_name)

                            file_stream = open(file_final, 'wb+')
                            FIRST_PACKET_RECEIVED = True
                            sequence = (sequence + 1) % 0x100

                        # data packet
                        # [data packet >>>]
                        # [<<< ACK]
                        elif not WAIT_FOR_END_PACKET:
                            self.rt.inc_valid_received_packets()
                            print("Packet " + str(sequence) + " >>>")
                            valid_data = data[:-2]
                            # last data packet
                            if self.rt.get_valid_received_packets() == self.rt.get_task_packets():
                                valid_data = valid_data[:self.rt.get_last_valid_packet_size()]
                                WAIT_FOR_EOT = True
                            self.rt.add_valid_received_bytes(len(valid_data))
                            file_stream.write(valid_data)
                            self.putc(ACK)
                            print("<<< ACK")

                            sequence = (sequence + 1) % 0x100

                        # final packet
                        # [<<< ACK]
                        else:
                            print("Packet End >>>")
                            self.putc(ACK)
                            print("<<< ACK")
                            break
        if file_stream is not None: file_stream.close()
        print("Task Done!")
        print("File: " + self.rt.get_task_name())
        print("Size: " + str(self.rt.get_task_size()) + "Bytes")
        print("Packets: " + str(self.rt.get_valid_received_packets()))
        return self.rt

    # Header byte
    def _make_edge_packet_header(self):
        _bytes = [ord(SOH), 0, 0xff]
        return bytearray(_bytes)

    def _make_data_packet_header(self, packet_size, sequence):
        assert packet_size in (128, 1024), packet_size
        _bytes = []
        if packet_size == 128:
            _bytes.append(ord(SOH))
        elif packet_size == 1024:
            _bytes.append(ord(STX))
        _bytes.extend([sequence, 0xff - sequence])
        return bytearray(_bytes)

    # Make check code
    def _make_send_checksum(self, data):
        _bytes = []
        crc = self.calc_crc_direct(data)
        # print("计算CRC原始: ", crc)
        _bytes.extend([crc >> 8, crc & 0xff])
        # print("_make_send_checksum() 将要计算的校验值的数据: ", bytesToHexString(data))
        return bytearray(_bytes)

    def _verify_recv_checksum(self, data):
        if isinstance(data, str):
            data = bytearray(data, 'utf-8')
        else:
            data = bytearray(data)
        their_sum = (data[-2] << 8) + data[-1]
        # print("_verify_recv_checksum() 将要计算的校验值的数据: ", bytesToHexString(data[:-2]))
        our_sum = self.calc_crc_direct(data[:-2])
        # print("计算CRC原始: ", our_sum)
        # print(f"_verify_recv_checksum() 校验结果: {their_sum}, {our_sum}")
        valid = bool(their_sum == our_sum)
        return valid, data

    @staticmethod
    def calc_crc_direct(data):
        crc = 0xFFFF
        for pos in data:
            crc ^= pos
            for i in range(8):
                if (crc & 1) != 0:
                    crc >>= 1
                    crc ^= 0xA001
                else:
                    crc >>= 1
        return ((crc & 0xff) << 8) + (crc >> 8)


class TaskState:
    ERROR = -99
    ABORTED = -1
    PREPARED = 0
    RUNNING = 1
    FINISHED = 2


class SendTask:
    def __init__(self):
        self._state = TaskState.PREPARED
        self._task_name = ""
        self._task_size = 0
        self._task_packets = 0
        self._last_valid_packets_size = 0
        self._sent_packets = 0
        self._missing_sent_packets = 0
        self._valid_sent_packets = 0
        self._valid_sent_bytes = 0

    def inc_sent_packets(self):
        self._sent_packets += 1

    def inc_missing_sent_packets(self):
        self._missing_sent_packets += 1

    def inc_valid_sent_packets(self):
        self._valid_sent_packets += 1

    def add_valid_sent_bytes(self, this_valid_sent_bytes):
        self._valid_sent_bytes += this_valid_sent_bytes

    def get_valid_sent_packets(self):
        return self._valid_sent_packets

    def get_valid_sent_bytes(self):
        return self._valid_sent_bytes

    def set_task_name(self, data_name):
        self._task_name = data_name

    def set_task_size(self, data_size):
        self._task_size = data_size
        self._task_packets = math.ceil(data_size / 1024)
        self._last_valid_packets_size = data_size % 1024


class ReceiveTask:
    def __init__(self):
        self._state = TaskState.PREPARED
        self._task_name = ""
        self._task_size = 0
        self._task_packets = 0
        self._last_valid_packets_size = 0
        self._received_packets = 0
        self._missing_received_packets = 0
        self._valid_received_packets = 0
        self._valid_received_bytes = 0

    def inc_received_packets(self):
        self._received_packets += 1

    def inc_missing_received_packets(self):
        self._missing_received_packets += 1

    def inc_valid_received_packets(self):
        self._valid_received_packets += 1

    def add_valid_received_bytes(self, this_valid_received_bytes):
        self._valid_received_bytes += this_valid_received_bytes

    def get_task_packets(self):
        return self._task_packets

    def get_last_valid_packet_size(self):
        return self._last_valid_packets_size

    def get_valid_received_packets(self):
        return self._valid_received_packets

    def get_valid_received_bytes(self):
        return self._valid_received_bytes

    def set_task_name(self, data_name):
        self._task_name = data_name

    def set_task_size(self, data_size):
        self._task_size = data_size
        self._task_packets = math.ceil(data_size / 1024)
        self._last_valid_packets_size = data_size % 1024

    def get_task_name(self):
        return self._task_name

    def get_task_size(self):
        return self._task_size


def call(v1, v2, v3):
    """
        基础回调
    :param v1:
    :param v2:
    :param v3: 文件名
    :return:
    """
    print("传输信息: ", v1, v2, v3)


if __name__ == '__main__':
    print("测试调试OTA")
    hmi_driver.starthmi("COM3")
    hmi_driver.startscreen()
    print("启动串口成功")
    print("开始发送文件")
    update._update_stm32("icopy_stm32_VS.bin", call)
    print("发送文件成功")
