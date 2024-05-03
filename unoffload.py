# pylint: disable=C0103, C0301

import datetime
import numpy as np
import networkx as nx
from computeNc import computeNc
from buildFci import buildFci
from S2id import S2id
from id2S import id2S
from numpy import inf
from computeDnTot import computeDnTot



np.seterr(divide='ignore', invalid='ignore')

def unoffload(Rcpu_old, Rmem_old, Fcm, M, lambd, Rs, S_edge_old, delay_increase_target, RTT, Ne, Cost_cpu_edge, Cost_mem_edge, dependency_paths_b, locked, u_limit):
    from offload import offload
    ## INITIALIZE VARIABLES ##
    #Rcpu_old (2*M,) vector of CPU req by instance-set at the cloud (:M) and at the edge (M:)
    #Rmem_old (2*M,) vector of Memory req by instance-set at the cloud (:M) and at the edge (M:)
    #Fcm (M,M)microservice call frequency matrix
    #M number of microservices
    #lambd user request rate
    #Rs (M,) vector of response size of microservices
    #S_edge_old (M,) vector of binary values indicating if the microservice is at the edge or not
    #delay_decrease_target delay reduction target
    #RTT fixed delay to add to microservice interaction in addition to the time depending on the response size
    #Ne cloud-edge network bitrate
    #Cost_cpu_edge cost of CPU at the edge
    #Cost_mem_edge cost of Memory at the edge
    #locked (M,) vector of binary values indicating if the microservice can not change state
    #u_limit maximum number of microservices upgrade to consider in the greedy iteraction (lower reduce optimality but increase computaiton speed)

    S_b_old = np.concatenate((np.ones(int(M)), S_edge_old))
    Rs = np.tile(Rs, 2)  # Expand the Rs vector to support matrix operations
    Fci_old = np.matrix(buildFci(S_b_old, Fcm, M)) # (2*M,2*M) instance-set call frequency matrix
    Nci_old = computeNc(Fci_old, M, 2)  # (2*M,) number of instance call per user request
    delay_old = computeDnTot(S_b_old, Nci_old, Fci_old, Rs, RTT, Ne, lambd, M)  # Total delay of the current configuration. It includes only network delays
    delay_target = delay_old + delay_increase_target
    Cost_cpu_edge_old_sum = Cost_cpu_edge * np.sum(S_b_old[M:] * Rcpu_old[M:]) # Total CPU cost
    Cost_mem_edge_old_sum = Cost_mem_edge * np.sum(S_b_old[M:] * Rmem_old[M:]) # Total Mem cost
    Cost_edge_old = Cost_cpu_edge_old_sum + Cost_mem_edge_old_sum # Total cost of old state
    locking = True if locked is not None else False
    if locking:
        locked_n = np.argwhere(locked==1).squeeze()
    S_b_void = np.concatenate((np.ones(M), np.zeros(M))) # (2*M,) state with no instance-set in the edge
    S_b_void[M-1] = 0  # User is not in the cloud
    S_b_void[2*M-1] = 1  # User is in the cloud
    S_edge_void = np.zeros(M)  # (M,) edge state with no instance-set in the edge
    S_edge_void[M-1] = 1  # User is at the edge
    Rcpu_void = np.zeros(2*M)
    Rmem_void = np.zeros(2*M)
    Rcpu_void[:M] = Rcpu_old[:M]+Rcpu_old[M:]
    Rcpu_void[M:] = np.zeros(M)
    Rmem_void[:M] = Rmem_old[:M]+Rmem_old[M:]
    Rmem_void[M:] = np.zeros(M)
    if locking:
        # status of locked microservices can not change
        S_b_void[locked_n+M] = S_b_old[locked_n+M]
        S_edge_void[locked] = S_b_old[locked_n+M]
        Rcpu_void[locked_n+M] = Rcpu_old[locked_n+M]
        Rmem_void[locked_n+M] = Rmem_old[locked_n+M]
        Rcpu_void[locked_n] = Rcpu_old[locked_n]
        Rmem_void[locked_n] = Rmem_old[locked_n]
    Fci_void = np.matrix(buildFci(S_b_void, Fcm, M))    # instance-set call frequency matrix of the void state
    Nci_void = computeNc(Fci_void, M, 2)    # number of instance call per user request of the void state
    delay_void = computeDnTot(S_b_void, Nci_void, Fci_void, Rs, RTT, Ne, lambd, M)
    delay_decrease_target = delay_void - delay_target 

    ## BUILDING OF DEPENDENCY PATHS ##
    if dependency_paths_b is None:
        G = nx.DiGraph(Fcm) # Create microservice dependency graph 
        dependency_paths_b = np.empty((0,M), int) # Storage of binary-based (b) encoded dependency paths

        ## COMPUTE "EDGE" DEPENDENCY PATHS ##
        for ms in range(M-1):
            paths_n = list(nx.all_simple_paths(G, source=M-1, target=ms)) 
            for path_n in paths_n:
                # path_n numerical id (n) of the microservices of the dependency path
                # If not all microservices in the path are in the edge this path is not a edge-only
                if not all(S_b_old[M+np.array([path_n])].squeeze()==1):
                    continue
                else:
                    path_b = np.zeros((1,M),int)
                    path_b[0,path_n] = 1 # Binary-based (b) encoding of the dependency path
                    dependency_paths_b = np.append(dependency_paths_b,path_b,axis=0)
    best_S_edge, best_cost, best_delay_decrease, best_cost_increase, n_rounds = offload(Rcpu_void, Rmem_void, Fcm, M, lambd, Rs, S_edge_void, delay_decrease_target, RTT, Ne, Cost_cpu_edge, Cost_mem_edge, dependency_paths_b, locked, u_limit)
    best_delay_increase = (delay_void-best_delay_decrease) - delay_old
    best_cost_decrease = Cost_edge_old - best_cost
    return best_S_edge, best_cost, best_delay_increase, best_cost_decrease, n_rounds

if __name__ == "__main__":
    # Define the input variables
    np.random.seed(150273)
    RTT = 0.0869    # RTT edge-cloud
    M = 30 # n. microservices
    delay_increase_target = 0.03    # requested delay reduction
    lambda_val = 20     # request per second
    Ne = 1e9    # bitrate cloud-edge
    
    S_edge_b = np.zeros(M)  # initial state. 
    S_edge_b[M-1] = 1 # Last value is the user must be set equal to one

    Cost_cpu_edge = 1 # cost of CPU at the edge
    Cost_mem_edge = 1 # cost of memory at the edge

    random=dict()
    random['n_parents'] = 3

    Fcm_range_min = 0.1 # min value of microservice call frequency 
    Fcm_range_max = 0.5 # max value of microservice call frequency 
    Rcpu_quota = 0.5    # CPU quota
    Rcpu_range_min = 1  # min value of requested CPU quota per instance-set
    Rcpu_range_max = 32 # max value of requested CPU quota per instance-set
    Rs_range_min = 1000 # min value of response size in bytes
    Rs_range_max = 50000   # max of response size in bytes
    
    Rs = np.random.randint(Rs_range_min,Rs_range_max,M)  # random response size bytes
    Rs[M-1]=0 # user has no response size
    
    # build dependency graph
    Fcm = np.zeros([M,M])   # microservice call frequency matrix
    for i in range(1,M-1):
        n_parent=np.random.randint(1,random['n_parents'])
        for j in range(n_parent):
            a = np.random.randint(i)
            Fcm[a,i]=1
        
    # set random values for microservice call frequency matrix
    for i in range(0,M-1):
        for j in range(0,M-1):
            Fcm[i,j]=np.random.uniform(0.1,0.5) if Fcm[i,j]>0 else 0
    Fcm[M-1,0] = 1  # user call microservice 0 (the ingress microservice)
    
    # add x dependency path at random
    G = nx.DiGraph(Fcm) # Create microservice dependency graph 
    dependency_paths_b = np.empty((0,M), int) # Storage of binary-based (b) encoded dependency paths
    for ms in range(M-1):
        paths_n = list(nx.all_simple_paths(G, source=M-1, target=ms)) 
        for path_n in paths_n:
            path_b = np.zeros((1,M),int)
            path_b[0,path_n] = 1 # Binary-based (b) encoding of the dependency path
            dependency_paths_b = np.append(dependency_paths_b,path_b,axis=0)
    l = len(dependency_paths_b)
    x = 10
    random_values = np.random.choice(range(l), size=x, replace=False)
    for j in random_values:
        S_edge_b = np.minimum(S_edge_b + dependency_paths_b[j],1)
    S_b = np.concatenate((np.ones(M), S_edge_b)) # (2*M,) full state
    S_b[M-1] = 0  # User is not in the cloud
    # set random values for CPU and memory requests
    Rcpu_void = (np.random.randint(32,size=M)+1) * Rcpu_quota
    Rcpu_void[M-1]=0   # user has no CPU request
    Rcpu_void = np.concatenate((Rcpu_void, np.zeros(M))) # (2*M,) vector of CPU requests for void state
    Rmem_void = np.zeros(2*M)
    S_b_void = np.concatenate((np.ones(M), np.zeros(M))) # (2*M,) state with no instance-set in the edge
    S_b_void[M-1] = 0  # User is not in the cloud
    S_b_void[2*M-1] = 1  # User is in the cloud
    Fci_void = np.matrix(buildFci(S_b_void, Fcm, M))    # instance-set call frequency matrix of the void state
    Nci_void = computeNc(Fci_void, M, 2)    # number of instance call per user request of the void state
    
    # compute Rcpu and Rmem for the current state
    # assumption is that cloud resource are reduced proportionally with respect to the reduction of the number of times instances are called
    Fci = np.matrix(buildFci(S_b, Fcm, M))    # instance-set call frequency matrix of the current state
    Nci = computeNc(Fci, M, 2)    # number of instance call per user request of the current state
    Rcpu = Rcpu_void.copy()
    Rmem = Rmem_void.copy()
    cloud_cpu_decrease = (1-Nci[:M]/Nci_void[:M]) * Rcpu_void[:M]   
    cloud_mem_decrease = (1-Nci[:M]/Nci_void[:M]) * Rmem_void[:M]  
    cloud_cpu_decrease[np.isnan(cloud_cpu_decrease)] = 0
    cloud_mem_decrease[np.isnan(cloud_mem_decrease)] = 0
    cloud_cpu_decrease[cloud_cpu_decrease==-inf] = 0
    cloud_mem_decrease[cloud_mem_decrease==-inf] = 0
    Rcpu[M:] = Rcpu[M:] + cloud_cpu_decrease # edge cpu increase
    Rmem[M:] = Rmem[M:] + cloud_mem_decrease # edge mem increase
    Rcpu[:M] = Rcpu[:M] - cloud_cpu_decrease # cloud cpu decrease
    Rmem[:M] = Rmem[:M] - cloud_mem_decrease # cloud mem decrease
    Cost_edge = Cost_cpu_edge * np.sum(Rcpu[M:]) + Cost_mem_edge * np.sum(Rmem[M:]) # Total edge cost of the current state
    
    # Call the unoffload function
    best_S_edge, best_cost_decrease, best_delay_increase, best_delta_cost, n_rounds = unoffload(Rcpu, Rmem, Fcm, M, lambda_val, Rs, S_edge_b, delay_increase_target, RTT, Ne, Cost_cpu_edge, Cost_mem_edge, None, None, 1)
    
    print(f"Result for unoffload:\n {np.argwhere(S_edge_b==1).squeeze()}, Cost: {Cost_edge}")
    print(f"Result for unoffload:\n {np.argwhere(best_S_edge==1).squeeze()}, Cost: {best_cost_decrease}, delay_increase: = {best_delay_increase}, cost_decrease: = {best_delta_cost}, rounds: = {n_rounds}")