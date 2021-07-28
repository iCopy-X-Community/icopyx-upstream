#!/usr/bin/env python3

# py3分离了str和bytes，这两个函数进行转换、
# 输入任意，输出str
def to_str(bytes_or_str):
    if isinstance(bytes_or_str, bytes):
        value = bytes_or_str.decode('utf-8')
    else:
        value = bytes_or_str
    return value    # Instance of str
# 输入任意，输出bytes


def to_bytes(bytes_or_str):
    if isinstance(bytes_or_str, str):
        value = bytes_or_str.encode('utf-8')
    else:
        value = bytes_or_str
    return value    # Instance of bytes


# 输入bytes，输出16进制字符串
def bytesToHexString(bs):
    return ''.join(['%02X,' % b for b in bs])