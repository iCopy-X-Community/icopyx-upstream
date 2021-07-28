#!/usr/bin/env python3

import serial
import threading
import time

# import batteryui
# import keymap
import re
import copy

from debug import *
from bytestr import *


DATA_GLO = ""  # 读取的数据
PARAM_EN = False  # 上一包存在参数
PARAM_GLO = ""  # 读取的参数
LABEL_RUN_READ = True
LABEL_READ_RUNNING = False
READ_A_RESP = 0  # 收到一个回应包标志位
NEED_HANDLE_OK = 0  # 处理心跳包后的ok回应标志位

label_processing = 0  # 处理过程标志，用于在非处理流程中自动清除

NEW_DATA = b""
PORT_DEFAULT = "/dev/ttyS0"
ser_instance = None
lock = threading.Lock()


# 硬件通信协议
serialrespok =  b"-> OK"
serialrespng =  b"-> PARA. ERR"
serialresprt =  b"-> CMD ERR, try: help"
serialreskey =  b"KEY"

cli_color =     b"C"
cli_position =  b"P"
cli_size =      b"S"
cli_id =        b"I"
cli_bl =        b"B"
cli_end =       b"A"
cli_cmd =       b"L"
cli_time =      b"T"

cli_stringstart =   0x02
cli_stringstop =    0x03

# 键码
SerialKeyCode = {
    # 按键码              #内部函数参数        #参数
    "UP_PRES!":          {"para": "UP",      "meth": None},
    "DOWN_PRES!":        {"para": "DOWN",    "meth": None},
    "RIGHT_PRES!":       {"para": "RIGHT",   "meth": None},
    "LEFT_PRES!":        {"para": "LEFT",    "meth": None},
    "OK_PRES!":          {"para": "OK",      "meth": None},
    "M1_PRES!":          {"para": "M1",      "meth": None},
    "M2_PRES!":          {"para": "M2",      "meth": None},
    "_PWR_CAN_PRES!":    {"para": "PWR",     "meth": None},
    "_ALL_PRES!":        {"para": "ALL",     "meth": None},
    "SHUTDOWN H3!":      {"para": "STDN",    "meth": None},
    "ARE YOU OK?":       {"para": "HTBT",    "meth": None},
    "CHARGING!":         {"para": "CHGI",    "meth": None},
    "DISCHARGIN!":       {"para": "CHGO",    "meth": None},
    "LOWBATTERY!!":      {"para": "LOBT",    "meth": None},
    "AUTO POWER ON!":    {"para": "APO",     "meth": None},
}

# 串口指令
Serialcommand = {
    # 指令                要传输的字符串        #参数
    "gotobl":            ("gotobl",            b""),
    "ledpm3":            ("ledpm3",            b"#LED:"),
    "presspm3":          ("presspm3",          b""),
    # pm3操作指令
    "turnonpm3":         ("turnonpm3",         b""),
    "turnoffpm3":        ("turnoffpm3",        b""),
    "restartpm3":        ("restartpm3",        b""),
    # 读取电源电压
    "volbat":            ("volbat",            b"#batvol:"),
    "pctbat":            ("pctbat",            b"#batpct:"),
    "volvcc":            ("volvcc",            b"#vccvol:"),
    # 查询充电状态
    "charge":            ("charge",            b"#charge:"),
    # h3开机完成指令
    "h3start":           ("h3start",           b""),
    "lcd2h3":            ("givemelcd",         b""),
    "lcd2st":            ("giveyoulcd",        b""),
    # RTC指令
    "givemetime":        ("givemetime",        b"#rtctime:"),
    "giveyoutime":       ("giveyoutime",       b""),
    # 显示指令
    "fillscreen":        ("fillscreen",        b""),
    "fillsquare":        ("fillsquare",        b""),
    "showsimbol":        ("showsimbol",        b""),
    "showstring":        ("showstring",        b""),
    "showpicture":       ("showpicture",       b""),
    "multicmd":          ("multicmd",          b""),
    "setbaklight":       ("setbaklight",       b""),
    # 关机心跳
    "i'm alive":         ("i'm alive",         b""),
    # 关机状态
    "shutdowning":       ("shutdowning",       b""),
    # 计划关机
    "plan2shutdown":     ("plan2shutdown",     b""),
    "version":           ("version",           b"#version:"),
    "idid":              ("idid",              b"#theid:"),
}


# 读取串口传入数据并等待传回状态
def run_serial_loop():
    global DATA_GLO, READ_A_RESP, LABEL_RUN_READ, LABEL_READ_RUNNING
    LABEL_READ_RUNNING = True
    wait_start_time = 0
    while LABEL_RUN_READ:
        # 等待外部处理回应包，处理后再读取下一包
        if READ_A_RESP == 0:
            try:
                buffer = ser_instance.readline()
                if len(buffer) <= 0 or buffer is None:
                    time.sleep(0.1)
                    continue
                DATA_GLO = buffer
            except Exception as e:
                print("ReadData() 异常 -> ", e)
                time.sleep(0.1)
                # 出现异常后，我们需要跳过处理下面的逻辑
                continue
            # 传入按钮处理
            if not DATA_GLO == b"\r\n":  # 硬件端会传一些空行回来，=-=太乱了，直接忽略掉不输出
                ViewMsgASCII("[seri]<- data received:")
                ViewMsgASCIIln(DATA_GLO)
            if _serial_key_handle():
                DATA_GLO = ""
            else:
                if DATA_GLO == b"\r\n":  # 空行不作为新包存在
                    pass
                else:
                    # ViewMsgASCIIln("[seri]<- 数据包获得，标注置位")
                    READ_A_RESP = 1  # 收到一个回应包
                    wait_start_time = time.time()
        else:
            # 当前有包，等待处理
            if time.time() - wait_start_time < 2:
                # 1秒内
                if label_processing == 1:
                    # 有人处理，等待时间延长
                    wait_start_time = time.time()
                time.sleep(0.01)
            else:
                # 超时没人处理，开始处理下一包
                READ_A_RESP = 0

    # 接收线程结束了，我们需要设置标志位
    LABEL_READ_RUNNING = False


# 处理按键事件，并调用按键处理
def _serial_key_handle():
    global DATA_GLO, NEED_HANDLE_OK
    if NEED_HANDLE_OK == 1:
        if DATA_GLO.startswith(b"\r"):
            pass
        if DATA_GLO.startswith(serialrespok):
            NEED_HANDLE_OK = 0
            return True
    # 处理心跳回复之后的ok和空行，处理后直接返回，不再传输给dxl
    for keycode in SerialKeyCode.keys():
        if DATA_GLO.find(to_bytes(keycode)) != -1:
            ViewMsgASCII("[comm]<- key methord received:")
            ViewMsgASCIIln(SerialKeyCode[keycode]["para"])
            # 读到了按键事件
            if SerialKeyCode[keycode]["para"] == "HTBT":
                _set_com(ser_instance, "i'm alive", "")
                NEED_HANDLE_OK = 1
            else:
                code = (SerialKeyCode[keycode]["para"])
                if code == "CHGI" or code == "CHGO":
                    is_charing = (code == "CHGI")
                    # We have a charing event...
                    # batteryui.notifyCharging(is_charing)
                    return
                # We have a key event...
                # keymap.key.onKey(code)
            return True
    return False


# 打开串口
def DOpenPort(port, bps, timeout):
    try:
        # 打开串口，并得到串口对象
        tmp_ser = serial.Serial(port, bps, timeout=timeout)
    except Exception as e:
        print("---异常---：", e)
        tmp_ser = None
    return tmp_ser


# 关闭串口
def DClosePort(port):
    if port is not None:
        port.close()


# 启动读取线程
def DOpenReadThread():
    """
        启动读取线程
    :return:
    """
    global LABEL_RUN_READ, READ_A_RESP, LABEL_READ_RUNNING

    if LABEL_READ_RUNNING:
        print("不允许多次开启接收线程。")
        return

    LABEL_RUN_READ = True  # 启用子线程运行条件
    LABEL_READ_RUNNING = False
    READ_A_RESP = 0  # 命令判断条件归零
    threading.Thread(target=run_serial_loop).start()
    # 堵塞等待启动
    while not LABEL_READ_RUNNING: time.sleep(0.1)


# 关闭读取线程
def DCloseReadThread():
    """
        关闭读取线程
    :return:
    """
    global ser_instance, READ_A_RESP, LABEL_RUN_READ
    LABEL_RUN_READ = False
    READ_A_RESP = 0
    while LABEL_READ_RUNNING: time.sleep(0.1)


# 对外的启动指令
def starthmi(port=PORT_DEFAULT):
    global ser_instance
    ser_instance = DOpenPort(port, 57600, None)
    if ser_instance is None:
        print("Serial not found, hmi disabled.")
        return
    if ser_instance.is_open:  # 判断串口是否成功打开
        DOpenReadThread()
        while not SetComReadBack("h3start", "", 5):
            pass
        ViewMsgASCIIln("[main]-> start ok!")


# 对外的关闭指令
def stophmi():
    global ser_instance, READ_A_RESP
    if ser_instance is None:
        print("Serial not found, hmi disabled.")
        return
    if ser_instance.is_open:  # 判断串口是否成功打开
        DClosePort(ser_instance)
        READ_A_RESP = 0
        DCloseReadThread()
        print("串口关闭完成")


# 对外的字节流模式指令
def ser_byte_mode():
    global ser_instance
    name = ser_instance.name
    DClosePort(ser_instance)
    DCloseReadThread()
    ser_instance = DOpenPort(name, 57600, None)


# 对外的命令模式指令
def ser_cmd_mode():
    global ser_instance
    if ser_instance.is_open:
        DOpenReadThread()


# 读取一行数据
def readline(get_str=False):
    if ser_instance is None:
        return None
    if LABEL_READ_RUNNING:
        print("不允许读取线程和外部读取操作一起进行。")
        return None
    line = ser_instance.readline()
    if get_str: return to_str(line)
    return to_bytes(line)


# 对外的字节流模式，读取一个byte
def ser_getc(size):
    return ser_instance.read(size) or None


# 对外的字节流模式，发送一个byte
def ser_putc(data):
    ser_instance.write(data)


# 对外的字节流模式，发送一个byte
def ser_flush():
    ser_instance.flushInput()


# 发送指令,从指令列表内查找指令并发送
def _set_com(port, comm, data):
    if port is None: return
    ViewMsgASCII("[comm]-> ")  # 日志
    ViewMsgASCII(Serialcommand[comm][0].encode("gbk"))  # 日志
    ViewMsgHEX(data)
    try:
        port.write(Serialcommand[comm][0].encode("gbk"))  # 写数据
        port.write(to_bytes(data))  # 写数据
        port.write("\r\n".encode("gbk"))
    except Exception as e:
        print("_set_com() -> 异常: ", e)
        return


# 处理参数包数据，从指令列表内寻找对应指令的回复格式，并提取有效数值
def _content_com(comm, param_data):
    global PARAM_GLO
    if comm in Serialcommand:
        if param_data.startswith(Serialcommand[comm][1]):
            temp_str = param_data.split(str.encode(':'), 1)
            PARAM_GLO = temp_str[1]
            return True
        else:
            return False


# 读取指令
# 返回1为ok包，0为ng包，2为参数包，3为无效数据，4为重发标志
def _read_resp_com(comm):
    global READ_A_RESP, DATA_GLO, PARAM_GLO
    if READ_A_RESP == 1:
        # 等待读取一个回应包
        if DATA_GLO.startswith(serialrespok):
            # 收到了ok包
            ViewMsgASCIIln("[comm]<- ok Package received")
            READ_A_RESP = 0  # 清空状态，开始下一包
            return 1
        elif DATA_GLO.startswith(serialrespng):
            # 收到了ng包
            ViewMsgASCIIln("[comm]<- ng Package received")
            READ_A_RESP = 0  # 清空状态，开始下一包
            return 0
        elif DATA_GLO.startswith(serialresprt):
            # 指令错误，需要重发
            ViewMsgASCIIln("[comm]<- need retransmit Package received")
            READ_A_RESP = 0  # 清空状态，开始下一包
            return 4
        elif DATA_GLO.startswith(b"\r"):
            # 收到了空行
            ViewMsgASCIIln("[comm]<- nodata Package received")
            READ_A_RESP = 0  # 清空状态，开始下一包
            return 3
        elif DATA_GLO.startswith(b"#"):
            # 收到了参数包
            ViewMsgASCIIln("[comm]<- para Package received")
            if _content_com(comm, DATA_GLO):
                # 解析了正确的参数包
                READ_A_RESP = 0  # 清空状态，开始下一包
                return 2
            else:
                # 参数包不正确
                READ_A_RESP = 0  # 清空状态，开始下一包
                return 3
        else:
            # 其他字符串，无效
            READ_A_RESP = 0  # 清空状态，开始下一包
            return 3
    else:
        # 串口未收到消息，无效
        return 3


# 发送指令并回读设备回应
# 返回当前行的状态，如果遇到有参数的则尝试获取参数
def SetComReadBack(comm, data, timeout):
    global PARAM_GLO, PARAM_EN, NEW_DATA, label_processing, ser_instance

    PARAM_EN = False
    startTime = time.time()
    palsetime = time.time()

    while time.time() - startTime < timeout:
        _set_com(ser_instance, comm, data)
        label_processing = 1  # 开始处理，阻止自动退出
        while True:  # 超时
            if time.time() - palsetime > 3:
                palsetime = time.time()
                ViewMsgASCIIln("[comm]-- RETRY!!")
                # 1秒重试一次
                break
            bak = _read_resp_com(comm)
            if bak == 2:
                # ParaGLO砍掉换行就是参数了
                # 不可以返回值，因为还需要处理ok包
                PARAM_GLO = re.sub("\r\n$", "", to_str(PARAM_GLO))
                PARAM_GLO = to_bytes(PARAM_GLO)
                ViewMsgASCII("[comm]<- para data:")
                ViewMsgASCIIln(PARAM_GLO)
                PARAM_EN = True
            elif bak == 1:
                # 收到了ok，也就是执行结束了，必须退出
                NEW_DATA = b""
                label_processing = 0  # 处理结束
                return True
            elif bak == 0:
                # 收到了ng，也就是执行结束了，必须退出
                label_processing = 0  # 处理结束
                return False
            elif bak == 4:
                # 收到了重发包，重发指令
                _set_com(ser_instance, comm, data)
            elif bak == 3:
                time.sleep(0.01)
    # 读到3的时候是无效包，必须重试到ok
    ViewMsgASCIIln("[comm]-- Times Out!!")
    # while结束，代表超时
    label_processing = 0  # 处理结束

    return False


def _addbaklight(string, bl):
    temp = string + cli_bl + bl.to_bytes(1, byteorder="big")
    return temp


def _addtime(string, bl):
    temp = string + cli_time + bl.to_bytes(4, byteorder="big")
    return temp


def _addend(string):
    temp = string + cli_end
    return temp


def _start_direct(cmd, data=""):
    """
        开启直接指令的发送
    :return:
    """
    try:
        lock.acquire()
        if ser_instance is None: return
        while not SetComReadBack(cmd, data, 5):
            pass
    finally:
        lock.release()


def _start_resp(cmd, data="", ParaEn_Reset=False):
    """
        开启需要回复的指令的发送
    :param cmd:
    :param data:
    :return:
    """
    try:
        lock.acquire()
        if ser_instance is None: return -1
        while not SetComReadBack(cmd, data, 5):
            pass
        global PARAM_EN
        if PARAM_EN == 1:
            if ParaEn_Reset:
                PARAM_EN = 0
            # 注意，这个是个全局变量，为了安全性，我们应该进行深拷贝
            return copy.deepcopy(PARAM_GLO)
        else:
            return -1
    finally:
        lock.release()


# 直接指令，不进行存储
def gotobl():
    if ser_instance is None: return
    ser_byte_mode()
    _set_com(ser_instance, "gotobl", "")


def startscreen():
    _start_direct("lcd2h3")


def stopscreen():
    _start_direct("lcd2st")


def shutdowning():
    _start_direct("shutdowning")


def presspm3():
    _start_direct("presspm3")


def ledpm3():
    return _start_resp("ledpm3", ParaEn_Reset=True) == b"1"


def restartpm3():
    _start_direct("restartpm3")


def turnonpm3():
    _start_direct("turnonpm3")


def turnoffpm3():
    _start_direct("turnoffpm3")


def setbaklight(bklt):
    if ser_instance is None: return
    temp_data = b""
    temp_data = _addbaklight(temp_data, bklt)
    temp_data = _addend(temp_data)
    _start_direct("setbaklight", temp_data)


def readbatvol():
    return int(_start_resp("volbat"))


def readbatpercent():
    return int(_start_resp("pctbat"))


def readvccvol():
    return int(_start_resp("volvcc"))


def readstid():
    return _start_resp("idid")


def readrtc():
    return _start_resp("givemetime")


def setrtc(rtctime):
    if ser_instance is None:
        return
    temp_data = b""
    temp_data = _addtime(temp_data, rtctime)
    temp_data = _addend(temp_data)
    return _start_direct("giveyoutime", temp_data)


def readhmiversion():
    return _start_resp("version")


def requestChargeState():
    return int(_start_resp("charge"))


def planToShutdown():
    _start_direct("plan2shutdown")
