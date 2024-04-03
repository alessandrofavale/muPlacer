import datetime
import numpy as np
from heuristic_autoplacer_unoffload import heuristic_autoplacer_unoffload

def autoplacer_unoffload(Rcpu, Rmem, Pcm_nocache, M, lambd, Rs, app_edge, max_delay_delta, RTT):
    x = datetime.datetime.now().strftime('%d-%m_%H:%M:%S')
    filename = f'unoffload_{x}.mat'
    #np.save(filename, arr=[Rcpu, Rmem, Pcm_nocache, M, lambd, Rs, app_edge, min_delay_delta, RTT])

    app_edge = np.append(app_edge, 1)  # add the user in app_edge (user is in the edge cluster)
    e = 2  # number of data center
    Ne = 1e9  # cloud-edge bit rate
    Ubit = np.arange(1, e+1) * M  # user position in the state vector
    # max_delay_delta = 0.2  # Maximum delay reduction
    Ce = np.inf
    Me = np.inf

    # Rcpu = np.append(Rcpu, 0)  # add the user in Rcpu vector
    # Rcpu = np.tile(Rcpu, e)  # edge and cloud microservices CPU, len(Rcpu) = 20 if M = 9 (M microservices + user)

    # Rmem = np.tile(np.zeros(M), e)  # Mem requested by instances to serve requests,
    # Rmem[Ubit] = 0  # set to zero Rmem for the user

    Rs = np.append(Rs, 0)  # add the user in Rs vector
    Rs = np.tile(Rs, e)  # edge and cloud microservices response size, len(Rs) = 20

    Rcpu_req = np.tile(np.zeros(M), e)  # seconds of CPU per request (set to zero for all microservices)
    Rcpu_req[int(Ubit[0])-1] = 0  # not used in our case, only if Rcpu_req is not filled with all zeros
    Rcpu_req[int(Ubit[1])-1] = 0  # not used in our case, only if Rcpu_req is not filled with all zeros

    best_S, best_dw, Dn, Tnce, Tnec, delta = heuristic_autoplacer_unoffload(Pcm_nocache, RTT, Rcpu_req, Rcpu, Rmem, Ce, Me, Ne, lambd, Rs, M, 0, 1, 2, app_edge, max_delay_delta)
    best_S_edge = best_S[M:2*M]  # takes only edge microservices
    print(best_S_edge)
    return best_S_edge, delta