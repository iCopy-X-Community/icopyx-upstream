#!/usr/bin/env python3

debug = 0


# 调试输出信息（hex）
def ViewMsgHEX(msg):
    if debug:
        for i in msg:
            print("%02x " % i, end="")
        print()


# 调试输出信息 (ascii)
def ViewMsgASCII(msg):
    if debug:
        print(msg, end="")


# 调试输出信息(ascii)+换行
def ViewMsgASCIIln(msg):
    if debug:
        print(msg)
