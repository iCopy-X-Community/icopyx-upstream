import os

def get_fws(typ):
    """
        获取固件包, 根据相应的类型
    :param typ: 类型, 可以是
                1、flash
                2、 pm3
                3、 stm32
    :return:
    """
    path = os.path.join("res", "firmware", typ)
    fw_list = []
    try:
        files = os.listdir(path)
        if len(files) == 0:
            return []
        for name in files:
            fw_list.append(os.path.join(path, name))
    except Exception:
        pass
    return fw_list
