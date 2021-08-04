"""
    更新程序的封装
"""
import os
import shutil
import time

import hmi_driver
import resources
import ymodem


def check_flash():
    """
        检测STM32的flash资源是否需要更新
    :return:
    """
    res = resources.get_fws("flash")
    res = list(filter(lambda item: "filelib" in item, res))
    return res


def check_stm32():
    """
        检测STM32的APP是否需要更新
    :return:
    """
    res = resources.get_fws("stm32")
    res = list(filter(lambda item: "app" in item or "stm32" in item, res))
    return res


def check_pm3():
    """
        检测PM3是否有固件需要更新
    :return:
    """
    res = resources.get_fws("pm3")
    res = list(filter(lambda item: "elf" in item, res))
    return res


def check_linux():
    """
        检测linux有没有啥需要更新的
    :return:
    """
    res = resources.get_fws("linux")
    res = list(filter(lambda item: "zip" in item or "linux" in item, res))
    return res


def check_all():
    """
        检测是否有更新包可以更新
    :return:
    """

    # 但凡有一个固件可以更新，我们就需要前往更新
    update_available_count = [
        len(check_flash()),
        len(check_stm32()),
        len(check_pm3()),
        len(check_linux()),
    ]

    return max(update_available_count) > 0


def enter_bl():
    """
        进入
    :return:
    """
    print("正在尝试进入BL")
    # 打开32的BL下载模式
    hmi_driver.gotobl()
    print("命令执行完成...")
    # 判断结果
    while True:
        try:
            line = hmi_driver.readline(True)
            print("获取到的行: ", line)

            if "BL Starting" in line:
                print("正在进入BL中...")
                continue

            if "BL Error" in line:
                print("BL进入失败")
                return False

            if "Wait for SEL" in line:
                print("进入BL成功")
                return True
        except Exception as e:
            print("进入BL时出现异常: ", e)
            break
    return False


def _send_start_cmd(mode):
    """
        发送启动指令
    :param mode:
    :return:
    """
    modeByte = int(mode + 0x30).to_bytes(length=1, byteorder='big', signed=True)
    hmi_driver.ser_putc(modeByte)


def _update_send_file(mode, file, call, addr=b"0x000000", retry_max=3):
    """
        发送文件到YModem
    :return:
    """
    print("开始进入app更新模式")
    if retry_max == 0:
        _send_start_cmd(3)
        return False
    print("更新模式: ", mode)

    # 发送相关的ascii，进入对应的更新模式
    _send_start_cmd(mode)

    print("更新模式进入成功...")

    if mode == 4:  # 选择4是flash数据，需要传输地址
        # 等待对方接收地址
        # 判断结果
        while True:
            try:
                line = hmi_driver.readline(True)
                print("获取到的行: ", line)

                if "Waiting for the Address" in line:
                    print("可以进行地址的传输，此次传输的地址是: ", addr)
                    time.sleep(0.1)
                    # 传输地址
                    # 发送写入的地址，开始写入
                    hmi_driver.ser_putc(addr + b"\r\n")
                    time.sleep(1)
                    continue

                if "ok,address =" in line:
                    print("地址传输完成，返回的地址是: ", line)
                    break

            except Exception as e:
                print("刷写FLASH出现异常: ", e)
                break

    hmi_driver.ser_flush()
    time.sleep(0.5)

    print("开始创建YModem对象进行文件传输")

    # 创建YMODEM的实现
    modem = ymodem.YModemSTM32(hmi_driver.ser_getc, hmi_driver.ser_putc)
    try:
        # 发送文件过去
        with open(file, mode="rb") as fd:
            print("开始发送文件")
            modem.send(
                fd,
                os.path.basename(file),
                file_size=os.path.getsize(file),
                callback=call
            )
            print("发送文件成功")
    except Exception as e:
        print("_update_send_file() -> ", e)

    need_retry = False

    # 读取结果判定
    while True:
        try:
            line = hmi_driver.readline(True)
            print("获取到的行: ", line)

            if "LARGE" in line:
                print("文件超出STM32的预期，不允许传输保存。")
                break

            retry_1 = "Verification failed" in line
            retry_2 = "Aborted by user" in line
            retry_3 = "Failed to receive the file" in line
            if retry_1 or retry_2 or retry_3:
                print("校验失败，将会重新启动发送")
                need_retry = True
                break

            if "Wait for SEL" in line:
                print("刷写完成！！！")
                return True

        except Exception as e:
            print("刷写固件出现异常: ", e)
            break

    if need_retry:
        return _update_send_file(mode, file, call, addr, retry_max - 1)

    return False


def _update_flash(file, call):
    """
        更新STM32的Flash
    :param file: 更新的文件
    :return:
    """
    try:
        if not enter_bl():
            raise Exception("进入BootLoader失败")
        _update_send_file(4, file, call)
        # 需要重启STM32
        hmi_driver.ser_flush()
        time.sleep(1)
        hmi_driver.ser_putc(b"3")
        # 发送完成后回到readline mode
        hmi_driver.ser_cmd_mode()
        return True
    except Exception as e:
        print(e)
    finally:
        # 务必删除文件
        os.remove(file)
    return False


def _update_stm32(file, call):
    """
        单独更新STM32的APP
    :param file:
    :param call:
    :return:
    """
    try:
        if not str(file).endswith(".bin"):
            raise Exception("不要使用不是bin文件的更新包啊垃圾开发者！")

        if not enter_bl():
            raise Exception("进入BootLoader失败")
        print("进入boot成功")
        _update_send_file(1, file, call)
        print("发送文件成功")
        # 需要重启STM32
        hmi_driver.ser_flush()
        time.sleep(1)
        hmi_driver.ser_putc(b"3")
        print("重启32成功")
        # 发送完成后回到readline mode
        hmi_driver.ser_cmd_mode()
        print("hmi_driver回到readline模式成功")
        return True
    except Exception as e:
        print(e)
    finally:
        # 务必删除文件
        os.remove(file)
    return False


def _update_stm32_flash_both(app_file, flash_file, call):
    """
        一起更新32的APP和闪存资源
    :param app_file:
    :param flash_file:
    :param call:
    :return:
    """
    try:
        if not enter_bl():
            raise Exception("进入BootLoader失败")
        _update_send_file(1, app_file, call)
        _update_send_file(4, flash_file, call)
        # 需要重启STM32
        hmi_driver.ser_flush()
        time.sleep(1)
        hmi_driver.ser_putc(b"3")
        # 发送完成后回到readline mode
        hmi_driver.ser_cmd_mode()
        return True
    except Exception as e:
        print(e)
    finally:
        # 务必删除文件
        os.remove(app_file)
        os.remove(flash_file)
    return False


def _unpack_zipfile(filename, extract_dir, call, name_force=None):
    """Unpack zip `filename` to `extract_dir`
    """
    import zipfile  # late import for breaking circular dependency

    if not zipfile.is_zipfile(filename):
        raise shutil.ReadError("%s is not a zip file" % filename)

    zip_tmp = zipfile.ZipFile(filename)
    try:
        uncompress_size = sum((file.file_size for file in zip_tmp.infolist()))
        extracted_size = 0
        for info in zip_tmp.infolist():
            name = info.filename
            extracted_size += info.file_size

            if name_force is not None:
                name = name_force
            call(extracted_size, uncompress_size, name)

            # don't extract absolute paths or ones with .. in them
            if name.startswith('/') or '..' in name:
                continue

            target = os.path.join(extract_dir, *name.split('/'))
            if not target:
                continue

            dirname = os.path.dirname(target)
            if not os.path.isdir(dirname):
                os.makedirs(dirname)

            if not name.endswith('/'):
                # file
                data = zip_tmp.read(info.filename)
                f = open(target, 'wb')
                try:
                    f.write(data)
                finally:
                    f.close()
                    del data
    finally:
        zip_tmp.close()


def _update_linux_dtb_resources(res, call):
    """
        更新linux
    :param res:
    :return:
    """
    try:
        # 直接执行指令，解压到目标目录
        _unpack_zipfile(res, "/boot", call, name_force="linux")
    except Exception as e:
        print("_update_linux_dtb_resources() -> ", e)
    finally:
        try:
            # 解压完了之后，删除源文件
            os.remove(res)
        except:
            pass


def start(listener):
    """
        开始进行更新
    :return:
    """

    def call(v1, v2, v3):
        """
            基础回调
        :param v1:
        :param v2:
        :param v3: 文件名
        :return:
        """
        listener({
            "finish": False,
            #       当前进度 总大小 文件名
            "progress": (v1, v2, v3)
        })

    # 判断是否同时有32和flash的固件需要更新
    stm32_fws = check_stm32()
    flash_fws = check_flash()

    # 如果两个固件同时都有，则一起刷，然后再重启
    if len(stm32_fws) > 0 and len(flash_fws) > 0:
        _update_stm32_flash_both(stm32_fws[0], flash_fws[0], call)
    elif len(stm32_fws) > 0:
        _update_stm32(stm32_fws[0], call)
    elif len(flash_fws) > 0:
        _update_flash(flash_fws[0], call)
    else:
        print("未发现有效的HMI系列固件更新")

    # 判断是否有linux的固件更新
    linux_fws = check_linux()
    if len(linux_fws) > 0:
        for file in linux_fws:
            if file.endswith(".zip"):  # 只支持zip压缩包
                _update_linux_dtb_resources(file, call)
    else:
        print("未发现linux的dtb相关的资源更新")

    listener({
        "finish": True,
    })
