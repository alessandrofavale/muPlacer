from autoplacer_offload import autoplacer_offload
from autoplacer_unoffload import autoplacer_unoffload
import numpy as np


RTT = 0.0884
max_delay_delta = 0.0626
app_edge = [1, 1, 1, 1, 1, 1, 1, 1, 1]
Rs = [2.0013e5, 0.9680e5, 1.0091e5,0.9220e5, 0.99642e5, 1.0184e5, 0.95019e5, 1.1302e5, 0.99908e5]
lambda_val = 35.7657
M = 10
Rcpu = [2, 0.5, 0.5, 0.5, 1, 0.5, 0.5, 0.5, 0.5, 0, 2, 0.5, 0.5, 0.5, 1, 0.5, 0.5, 0.5, 0.5, 0]
Rmem = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
Fcm = np.array([[0,0.2310,0.2260,0.2200,0.2160,0,0,0,0,0],
                [0,0,0,0,0,0,0,0,0,0],
                [0,0,0,0,0,0.2100,0,0,0,0],
                [0,0,0,0,0,0,0,0,0.1990,0],
                [0,0,0,0,0,0,0.2050,0.1960,0,0],
                [0,0,0,0,0,0,0,0,0,0],
                [0,0,0,0,0,0,0,0,0,0],
                [0,0,0,0,0,0,0,0,0,0],
                [0,0,0,0,0,0,0,0,0,0],
                [1,0,0,0,0,0,0,0,0,0]])

result = autoplacer_unoffload(Rcpu, Rmem, Fcm, M, lambda_val, Rs, app_edge, max_delay_delta, RTT)
print(result[0])