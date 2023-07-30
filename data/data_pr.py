import os
import torch
import shutil
import h5py
import numpy as np
from scipy.spatial.distance import cdist

# with h5py.File(f"bike_data.h5", 'r') as hf:
#     data_pick = hf[f'bike_pick'][:]
#     for name in hf:
#         print(name)
# with h5py.File(f"taxi_data.h5", 'r') as hf:
#     data_drop = hf[f'taxi_drop'][:]
#
# with np.load('pems08.npz') as data:
#     a = data
#
# # 加载npz文件
# data = np.load('pems08.npz')
#
# # 将数据转换为h5格式
# with h5py.File('pems08.h5', 'w') as hf:
#     for key in data:
#         hf.create_dataset(key, data=data[key])
# with h5py.File('pems08.h5', 'r') as hf:
#     # 获取并打印所有数据集的名称
#     for name in hf:
#         print(name)
# with h5py.File(f"pems08.h5", 'r') as hf:
#     data_0 = hf[f'data'][:]
#     data_1 = hf[f'data'][0:4368,:,0]
# with h5py.File(f"pems04.h5", 'r') as hf:
#     data_3 = hf[f'data'][:]
#     data_4 = hf[f'data'][0:4368,:,0]

a=3

def aaa(data,target):
    def bbb(data,target,start,p,f):
        if target <0:
            return
        if target == 0:
            f.append(p)
            return
        for i in range(start, len(data)):
            bbb(data, target-data[i], i, p+[data[i]], f)
    f = []
    data.sort()
    bbb(data, target, 0, [], f)
    return f

print(aaa([1,8,7,0,1,5,1], 10))

asdx = 123
