import numpy as np
import networkx as nx
from S2id import S2id
from delayMat import delayMat
from id2S import id2S

#   path adding heuristic algorithm (PAMP)

#   RTT : RTT cloud edge
#   Ne : cloud edge bit rate
#   lambda : user request frequency
#   Rs : byte lenght of the response of microservices
#   Pcm : microservice calling probabilities matrix
#   Nc : number of time a microservice is called per request
#   M : number of microservices
#   Rcpu_req : CPU seconds for internal functions
#   Ce, Me, Ne : CPU, Mem and net capacity of the edge
#   Rcpu, Rmem : CPU and Mem requested by microservices
#   db = 0 if no db
#   e : number of datacenters
#   app_edge: microservices already at the edge cloud
#   min_delay_delta: minimum delay reduction

# _b : binary encoding of a set of nodes/services 
# _id : identifier of a set of nodes come out from binary encoding
# _n : identifiers of the nodes of a set

def heuristic_autoplacer_unoffload(Pcm, RTT, Rcpu_req, Rcpu, Rmem, Ce, Me, Ne, lambd, Rs, M, db, horizon, e, app_edge, max_delay_delta):
    # SEARCH ALL PATHS FROM USER TO SERVICES

    # Create the graph of the mesh with probabilities
    G = nx.DiGraph(Pcm)
    # user is the last microservice, root in the graph
    user = G.number_of_nodes()
    # last microservice (user is the root of the graph)
    last_n = user
    # define the variable for all paths
    paths_n = []

    # FIND ALL PATHS WITH THE LEAF MICROSERVICE IN CLOUD CLUSTER ("valid" path)
    
    for s in range(1, last_n):
        # Find all paths in the graph
        paths = list(nx.all_simple_paths(G, source=user-1, target=s-1))
        # define a variable for "valid" path
        valid_path = True 
        # Check if the path is "valid"
        for path in paths:
            app_edge_values = app_edge[path[-1]]
            # If all microservices in the path have app_edge_values == 0, this path is not "valid"
            if app_edge_values == 0:
                valid_path = False
                break
        
        # Add the path if it's "valid" in paths_n
        if valid_path:
            paths_n.extend(paths)

    # CREATE THE LIST OF POSSIBLE ID SUBGRAPH WITH THE LEAF MICROSERVICE IN CLOUD CLUSTER
    subgraphs_id_origin = [S2id(app_edge)] # The origin subgraph is the actual configuration running
    # Next cycle will increase it adding possible subgraphs
    for i in range(len(paths_n)):
        SG = paths_n[i]  # SG microservices combination of i-th paths.
        # SG[j,k] nodes of the k path of the j-th combination of i paths
        subgraph_b = np.zeros(user)  # inizialize the subgraph_b vector
        subgraph_b[SG] = 1  # assign value 1 in subgraph_b vector facing subgraph_n
        subgraph_id = S2id(subgraph_b)  # convert the subgraph in subgraph_id
        # Check if there is already the current subgraph_id in the list (subgraph_id_origin)
        if subgraph_id not in subgraphs_id_origin:
            subgraphs_id_origin.append(subgraph_id)  # add the current subgraph in the id list


    # GREEDY ADDITION OF NODES (SERVICE) OF SUBGRAPHS TO AN EDGE (PAMP ALGORITHM)
    best_edge_Sid = []  # define the variable for the best edge state
    for h in range(2, e+1):
        # repeat the algorithm for every edge data center, considering in each
        # iteration a subproblem made by only a cloud and an edge
        subgraphs_id = subgraphs_id_origin.copy()
        Scur_edge_origin_id = subgraphs_id[0] # initial state of an edge node with only user at the edge.
        # To get the id of a state that includes also the cloud it is necessary to add cloud_shift
        H = [] # history vector
        Rcpu_edge = np.array(Rcpu[(h - 1) * M:h * M])
        Rmem_edge = np.array(Rmem[(h - 1) * M:h * M])
        #Scur_edge_origin_b = np.array(app_edge)
        Scur_edge_origin_b = np.zeros(M)
        Rcpu_origin = np.sum(Scur_edge_origin_b * Rcpu_edge)
        Rmem_origin = np.sum(Scur_edge_origin_b * Rmem_edge)
        Sorigin = np.zeros(2*M)
        Sorigin[:M-1] = 1
        Sorigin[M:2*M] = app_edge
        dorigin = delayMat(Sorigin, Pcm, Rcpu, Rcpu_req, RTT, Ne, lambd, Rs, M, 2)[0]
        subgraphs_id = subgraphs_id[1:]
        Scur_edge_id = 2 # only user
        while True:
            nsg = len(subgraphs_id) # next subgraph
            subgraphs_weights = -np.inf * np.ones(nsg)
            subgraphs_costs = -np.inf * np.ones(nsg)
            subgraphs_r = np.inf * np.ones(nsg)
            Scur_edge_b = id2S(Scur_edge_id, 2**M)
            subgraph_d = np.inf * np.ones(nsg)

            for i in range(nsg):
                sg_id = subgraphs_id[i]
                Snew_edge_id = np.bitwise_or(sg_id-1, Scur_edge_id-1) + 1 # new edge state adding subgraph sg_id
                Snew_edge_b = id2S(Snew_edge_id, 2**M)
                Rcpu_new = np.sum(Snew_edge_b * Rcpu_edge)
                Rmem_new = np.sum(Snew_edge_b * Rmem_edge)
                # This is the check in line 10 of PAMP code in the paper
                if Rcpu_new > Ce or Rmem_new > Me:
                    subgraphs_weights[i] = -np.inf
                    subgraphs_r[i] = 0
                    continue
                cost_cpu = Rcpu_new - Rcpu_origin
                cost_mem = Rmem_new - Rmem_origin
                # cost is the w(pi) inside the paper
                # cost = max(cost_cpu / Ce + cost_mem / Me, 1e-6) # cost proportional to consumed resources. 1e-6 used to avoid 0
                cost = cost_cpu
                # Snew_edge_id+cloud_shift is the id of the state made by a
                # cloud and an edge
                Snew = np.zeros(2*M)
                Snew[:M-1] = 1
                Snew[M:] = Snew_edge_b
                # dnew is Dm(U) inside the paper
                dnew = delayMat(Snew, Pcm, Rcpu, Rcpu_req, RTT, Ne, lambd, Rs, M, 2)[0]
                if dnew == np.inf:
                    subgraphs_weights[i] = -np.inf
                    subgraphs_r[i] = 0
                    continue
                # this is the v(pi) inside the paper
                # r = 1 / dnew
                r = dnew - dorigin
                if r > max_delay_delta:
                    subgraphs_weights[i] = 0
                    subgraphs_costs[i] = np.inf
                else:
                    # This is the delta variable in the paper
                    subgraphs_weights[i] = min(r, max_delay_delta) / cost # delta = v(pi)/w(pi)
                    subgraphs_costs[i] = cost
                subgraphs_r[i] = r
                subgraph_d[i] = dnew
            I = np.argmax(subgraphs_weights)
            best_sg = subgraphs_id[I]
            Scur_edge_id = np.bitwise_or(best_sg-1, Scur_edge_id-1) + 1 # update edge status inserting the nodes of the best subgraph
            H.append(np.array([Scur_edge_id, subgraphs_r[I], subgraphs_costs[I], subgraphs_weights[I], subgraph_d[I]]))
            PR = []
            for pr in range(nsg):
                if np.bitwise_and(subgraphs_id[pr]-1, Scur_edge_id-1) + 1 == subgraphs_id[pr]:
                    PR.append(pr)
            subgraphs_id = [subgraphs_id[pr] for pr in range(nsg) if pr not in PR]
            if len(subgraphs_id) == 0:
                # all subgraphs considered
                break

        # resource exhaustion
        if len(H) == 0:
            # no capacity for edge computing
            best_edge_Sid[h] = Scur_edge_origin_id
        else:
            cur_delay = H[-1][4] # current delay, because last solution will contain the current edge microservices
            # select in H matrix the configuration in which the increment of the delay respect to cur_delay is less than max_delay_delta
            I = [i for i in range(len(H)) if H[i][4] - cur_delay < max_delay_delta]
            # select the one with less usage of CPU
            I2 = np.argmin([H[i][2] for i in I])

            if len(I) == 0:
                best_edge_Sid.append(H[-1][0])
            else:
                best_edge_Sid.append(H[I[I2]][0])

    # BUILD THE BEST_S VECTOR
    best_S = np.zeros(e*M)
    best_S[:M-1] = 1
    best_S[M-1] = 0
    for h in range(2, e+1):
        best_S[(h-1)*M:h*M] = id2S(int(best_edge_Sid[h-2]), 2**M)
    best_dw, Dn, Tnce, Tnec, Di, Nc = delayMat(best_S, Pcm, Rcpu, Rcpu_req, RTT, Ne, lambd, Rs, M, e)
    if len(I) == 0:
        delta = 0
    else:
        delta = H[I[I2]][4] - H[-1][4]
    
    return best_S, best_dw, Dn, Tnce, Tnec, delta