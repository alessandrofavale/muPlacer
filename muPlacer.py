import time
from kubernetes import client, config
from prometheus_api_client import PrometheusConnect
import numpy as np
import subprocess
import threading
import csv
from conf import *
from OE_PAMP_unoff import *
from OE_PAMP_off import *
from IA_placement import *
from random_placement import *
from mfu_placement import *


PERIOD = 3 # Rate of queries in minutes
#SLO_MARGIN_OFFLOAD = 0.9 # SLO increase margin
HPA_STATUS = 0 # Initialization HPA status (0 = HPA Not running, 1 = HPA running)
HPA_MARGIN = 1.05 # HPA margin
RTT = 86e-3 #  Initialization Round Trip Time in seconds
AVG_DELAY = 0 # Average user delay
TRAFFIC = 0 # Cloud-edge traffic
RCPU = np.array([]) # CPU provided to each microservice
RCPU_EDGE = 0 # CPU provided to each microservice in the edge cluster
RCPU_CLOUD = 0 # CPU provided to each microservice in the cloud cluster

# Connect to Prometheus
prom = PrometheusConnect(url=PROMETHEUS_URL, disable_ssl=True)

# Get microservice (app) names of the application
def get_app_names():
    # Get all app names inside the namespace
    command1 = f'kubectl get deployment -n {NAMESPACE} -o custom-columns=APP:.metadata.labels.app --no-headers=true | grep -v "<none>" | sort -t \'s\' -k2,2n | uniq;'
    result1 = subprocess.run(command1, shell=True, check=True, text=True, stdout=subprocess.PIPE)
    output1 = result1.stdout
    # Split the output by newline, remove any leading/trailing whitespaces, and filter out empty strings
    app_names = [value.strip() for value in output1.split('\n') if value.strip()]
    return app_names

APP_EDGE = np.zeros(len(get_app_names()), dtype=int) # Microservice in the edge cluster

# Function that get the average delay from istio-ingress
def get_avg_delay():
    while True:
        global AVG_DELAY
        query_avg_delay = f'sum by (source_workload) (rate(istio_request_duration_milliseconds_sum{{source_workload="istio-ingressgateway", reporter="source", response_code="200"}}[1m])) / sum by (source_workload) (rate(istio_request_duration_milliseconds_count{{source_workload="istio-ingressgateway", reporter="source", response_code="200"}}[1m]))'
        result_query = prom.custom_query(query=query_avg_delay)
        if result_query:
            for result in result_query:
                avg_delay = result["value"][1]  # avg_delay result
                if avg_delay == "NaN":
                    AVG_DELAY = 0
                    if SAVE_RESULTS == 1:
                        save_delay(AVG_DELAY)
                    time.sleep(1)
                else:
                    AVG_DELAY = round(float(avg_delay),2)
                    if SAVE_RESULTS == 1:
                        save_delay(AVG_DELAY)
                    time.sleep(1)    

# Function that take the requests per second
def get_lamba():
    # Query to obtain requests per second
    query_lambda = f'sum by (source_app) (rate(istio_requests_total{{source_app="istio-ingressgateway", source_cluster="cluster2", reporter="destination", response_code="200"}}[{PERIOD}m]))'
    query_result = prom.custom_query(query=query_lambda)
    if query_result:
        for result in query_result:
            return float(result["value"][1]) # Get the value of lambda

# Function that get the cpu provided to each microservices 
def get_Rcpu():
    global RCPU, RCPU_EDGE, RCPU_CLOUD
    while True:
        app_names = get_app_names() # Get app names with the relative function
        Rcpu_cloud = np.full(len(app_names), -1, dtype=float) # Initialize Rcpu_cloud
        Rcpu_edge = np.full(len(app_names), -1, dtype=float) # Initialize Rcpu_edge
        
        # Query to obtain cpu provided to each microservice in the cloud cluster
        query_cpu_cloud = f'sum by (container) (last_over_time(kube_pod_container_resource_limits{{namespace="{NAMESPACE}", resource="cpu", container!="istio-proxy", cluster!="cluster2"}}[1m]))'
        cpu_cloud_results = prom.custom_query(query=query_cpu_cloud)
        if cpu_cloud_results:
            for result in cpu_cloud_results:
                Rcpu_value = result["value"][1] # Get the value of Rcpu
                Rcpu_cloud[app_names.index(result["metric"]["container"])] = float(Rcpu_value) # Insert the value inside Rcpu_cloud array
        
        # Query to obtain cpu provided to each microservice in the edge cluster
        query_cpu_edge = f'sum by (container) (last_over_time(kube_pod_container_resource_limits{{namespace="{NAMESPACE}", resource="cpu", container!="istio-proxy", cluster="cluster2"}}[1m]))'
        cpu_edge_results = prom.custom_query(query=query_cpu_edge)
        if cpu_edge_results:
            for result in cpu_edge_results:
                Rcpu_value = result["value"][1] # Get the value of Rcpu
                Rcpu_edge[app_names.index(result["metric"]["container"])] = float(Rcpu_value) # Insert the value inside Rcpu_cloud array
        
        Rcpu_edge_graphs = Rcpu_edge.copy() # Copy Rcpu_edge array to Rcpu_edge_graphs array
        
        # Check for missing values in Rcpu_edge and replace them with corresponding values from Rcpu_cloud
        for i, value in enumerate(Rcpu_edge):
            if value == -1:
                Rcpu_edge[i] = Rcpu_cloud[i]

        # Check for missing values in Rcpu_edge_graphs and replace them with 0 for graphs
        for i, value in enumerate(Rcpu_edge_graphs):
            if value == -1:
                Rcpu_edge_graphs[i] = 0

        # Save Rcpu values of edge and cloud cluster
        RCPU_EDGE = np.sum(Rcpu_edge_graphs)
        RCPU_CLOUD = np.sum(Rcpu_cloud)
        RCPU = np.concatenate((np.append(Rcpu_cloud, 0), np.append(Rcpu_edge, 0))) # Rcpu values of each microservices (cloud+edge)
        time.sleep(5)
    #return Rcpu

# Function that get the memory provided to each microservices
def get_Rmem():
    app_names = get_app_names() # Get app names with the relative function
    Rmem_cloud = np.full(len(app_names), -1, dtype=float) # Initialize Rmem_cloud
    Rmem_edge = np.full(len(app_names), -1, dtype=float) # Initialize Rmem_edge
    
    # Query to obtain cpu provided to each microservice in the cloud cluster
    query_mem_cloud = f'sum by (container) (kube_pod_container_resource_limits{{namespace="{NAMESPACE}", resource="memory", container!="istio-proxy",cluster!="cluster2"}})'
    mem_cloud_results = prom.custom_query(query=query_mem_cloud)
    if mem_cloud_results:
        for result in mem_cloud_results:
            Rmem_value = result["value"][1] # Get the value of Rmem
            Rmem_cloud[app_names.index(result["metric"]["container"])] = float(Rmem_value) # Insert the value inside Rmem_cloud array
    else:
        Rmem_cloud = np.zeros(len(app_names))

    # Query to obtain cpu provided to each microservice in the edge cluster
    query_mem_edge = f'sum by (container) (kube_pod_container_resource_limits{{namespace="{NAMESPACE}", resource="memory", container!="istio-proxy",cluster="cluster2"}})'
    mem_edge_results = prom.custom_query(query=query_mem_edge)
    if mem_edge_results:
        for result in mem_edge_results:
            Rmem_value = result["value"][1] # Get the value of Rmem
            Rmem_edge[app_names.index(result["metric"]["container"])] = float(Rmem_value) # Insert the value inside Rmem_cloud array
    else:
        Rmem_cloud = np.zeros(len(app_names))

    # Check for missing values in Rmem_edge and replace them with corresponding values from Rmem_cloud
    for i, value in enumerate(Rmem_edge):
        if value == -1:
            Rmem_edge[i] = Rmem_cloud[i]

    Rmem_edge = np.append(Rmem_edge, 0) # Add user with Rmem = 0
    Rmem_cloud = np.append(Rmem_cloud, 0) # Add user with Rmem = 0
    Rmem = np.concatenate((Rmem_cloud, Rmem_edge)) # Rmem values of each microservices (cloud+edge)
    return Rmem

# Function that get the microservice names already in edge cluster
def get_app_edge():
    global APP_EDGE
    while True:
        #app_edge = np.zeros(len(get_app_names()), dtype=int) # Initialize array with zeros with lenght equal to the number of microservices (the last value is for istio-ingress)
        command = f'kubectl get deployments.apps -n edge --context {CTX_CLUSTER2} -o custom-columns=APP:.metadata.labels.app --no-headers=true | grep -v "<none>" | sort | uniq' # Get microservice offloaded
        result = subprocess.run(command, shell=True, check=True, text=True, stdout=subprocess.PIPE)
        output = result.stdout
            # Split the output by newline, remove any leading/trailing whitespaces, and filter out empty strings
        app_names_edge = [value.strip() for value in output.split('\n') if value.strip()]
        for microservice in app_names_edge:
            #app_edge[get_app_names().index(microservice)] = 1 # Set value for microservice in edge to 1        
            APP_EDGE[get_app_names().index(microservice)] = 1 # Set value for microservice in edge to 1
        time.sleep(10)
    #return app_edge

# Function that find probabilities between each microservice including istio-ingress
def get_Pcm():
    app_names = get_app_names() # Get app names with the relative function
    
    # add app name of istio ingress in app_names list for Pcm matrix
    app_istio_ingress = "istio-ingressgateway"
    app_names = app_names + [app_istio_ingress] # Add istio-ingress to app_names list

    # Create a matrix with numpy to store calling probabilities
    Pcm = np.zeros((len(app_names), len(app_names)), dtype=float)

    # Find and filter significant probabilities
    for i, src_app in enumerate(app_names):
        for j, dst_app in enumerate(app_names):
            # Check if source and destination apps are different
            if src_app != dst_app:
                # total requests that arrive to dst microservice from src microservice
                query1 = f'sum by (destination_app) (rate(istio_requests_total{{source_app="{src_app}",reporter="destination", destination_app="{dst_app}",response_code="200"}}[{PERIOD}m]))'
                
                #total requests that arrive to the source microservice
                if src_app != "istio-ingressgateway":
                    # Query for istio-ingress
                    query2 = f'sum by (source_app) (rate(istio_requests_total{{reporter="destination", destination_app="{src_app}",response_code="200"}}[{PERIOD}m]))'
                else:
                    query2 = f'sum by (source_app) (rate(istio_requests_total{{source_app="{src_app}",reporter="destination", destination_app="{dst_app}",response_code="200"}}[{PERIOD}m]))' 

                #print(query1)
                #print(query2)
                r1 = prom.custom_query(query=query1)
                r2 = prom.custom_query(query=query2)

                # Initialize variables
                calling_probability = None
                v = 0
                s = 0

                # Extract values from queries
                if r1 and r2:
                    for result in r1:
                        if float(result["value"][1]) == 0: 
                            continue
                        v = result["value"][1]
                        #print("v =", v)
                    for result in r2:
                        if float(result["value"][1]) == 0:
                            continue
                        s = result["value"][1]
                        #print("s =", s)

                    # Calculate calling probabilities
                    if s == 0 or s == "Nan":
                        calling_probability = 0 # If there isn't traffic
                    else:
                        calling_probability = float(v) / float(s)
                        if calling_probability > 0.98:
                            calling_probability = 1
                        
                        calling_probability = round(calling_probability, 3)  # Round to 4 decimal places
                        Pcm[i, j] = calling_probability # Insert the value inside Pcm matrix              
    #print(Pcm)
    return Pcm

# Function that take the response size of each microservice
def get_Rs():
    app_names = get_app_names() # Get app names with the relative function

    Rs = np.zeros(len(app_names), dtype=float) # inizialize Rs array

    # app_names combined with OR (|) for prometheus query
    combined_names = "|".join(app_names)

    # Query to obtain response size of each microservice    
    query_Rs = f'sum by (destination_app) (increase(istio_response_bytes_sum{{response_code="200", destination_app=~"{combined_names}", reporter="source"}}[{PERIOD}m]))/sum by (destination_app) (increase(istio_response_bytes_count{{response_code="200", destination_app=~"{combined_names}", reporter="source"}}[{PERIOD}m]))'
    r1 = prom.custom_query(query=query_Rs)
    if r1:
        for result in r1:
            Rs_value = result["value"][1]
            if Rs_value == "NaN":
                Rs[app_names.index(result["metric"]["destination_app"])] = 0 # If there isn't traffic
            else:
                Rs[app_names.index(result["metric"]["destination_app"])] = float(Rs_value)
    return Rs

# Function that checks if some HPA is running for both clusters
def check_hpa():
    # Load the kube config file for the first cluster
    config.load_kube_config(context="kubernetes-admin@cluster.local")
    
    # Create the API object for the first cluster
    api_cluster1 = client.AppsV1Api()
    autoscaling_api_cluster1 = client.AutoscalingV1Api()

    # Load the kube config file for the second cluster
    config.load_kube_config(context="kubernetes-admin1@cluster1.local")
    
    # Create the API object for the second cluster
    api_cluster2 = client.AppsV1Api()
    autoscaling_api_cluster2 = client.AutoscalingV1Api()

    while True:
        global HPA_STATUS
        # Get the list of all deployments in the first cluster
        deployments_cluster1 = api_cluster1.list_namespaced_deployment(namespace=NAMESPACE)

        # Get the list of all deployments in the second cluster
        deployments_cluster2 = api_cluster2.list_namespaced_deployment(namespace=NAMESPACE)

        all_hpa_satisfy_condition = True  # Assume initially that all HPAs satisfy the condition

        # Check the first cluster
        for deployment in deployments_cluster1.items:
            deployment_name = deployment.metadata.name

            # Get the list of associated HPAs for the deployment in the first cluster
            associated_hpas = autoscaling_api_cluster1.list_namespaced_horizontal_pod_autoscaler(namespace=NAMESPACE)

            for hpa in associated_hpas.items:
                hpa_name = hpa.metadata.name

                # Check if the HPA is associated with the current deployment
                if hpa.spec.scale_target_ref.name == deployment_name:
                    # Get the target CPU utilization percentage
                    cpu_utilization = hpa.spec.target_cpu_utilization_percentage

                    # Get the current status of the HPA
                    hpa_status = autoscaling_api_cluster1.read_namespaced_horizontal_pod_autoscaler_status(name=hpa_name, namespace=NAMESPACE)
                    current_cpu_utilization_percentage = hpa_status.status.current_cpu_utilization_percentage

                    if current_cpu_utilization_percentage is None:
                        current_cpu_utilization_percentage = 0

                    # Check if the current CPU usage is less than the target CPU for the HPA
                    if current_cpu_utilization_percentage >= cpu_utilization * HPA_MARGIN:
                        # If an HPA doesn't satisfy the condition, set the flag to False and break out of the loop
                        all_hpa_satisfy_condition = False
                        break

        # Check the second cluster
        for deployment in deployments_cluster2.items:
            deployment_name = deployment.metadata.name

            # Get the list of associated HPAs for the deployment in the second cluster
            associated_hpas = autoscaling_api_cluster2.list_namespaced_horizontal_pod_autoscaler(namespace=NAMESPACE)

            for hpa in associated_hpas.items:
                hpa_name = hpa.metadata.name

                # Check if the HPA is associated with the current deployment
                if hpa.spec.scale_target_ref.name == deployment_name:
                    # Get the target CPU utilization percentage
                    cpu_utilization = hpa.spec.target_cpu_utilization_percentage

                    # Get the current status of the HPA
                    hpa_status = autoscaling_api_cluster2.read_namespaced_horizontal_pod_autoscaler_status(name=hpa_name, namespace=NAMESPACE)
                    current_cpu_utilization_percentage = hpa_status.status.current_cpu_utilization_percentage

                    if current_cpu_utilization_percentage is None:
                        current_cpu_utilization_percentage = 0

                    # Check if the current CPU usage is less than the target CPU for the HPA
                    if current_cpu_utilization_percentage >= cpu_utilization * HPA_MARGIN:
                        # If an HPA doesn't satisfy the condition, set the flag to False and break out of the loop
                        all_hpa_satisfy_condition = False
                        break

        if all_hpa_satisfy_condition:
            HPA_STATUS = 0
        else:
            HPA_STATUS = 1

        # HPA metrics refresh every 15 seconds
        time.sleep(15)

# Function that get the RTT cloud-edge
def get_RTT():
    global RTT
    while True:
        RTT_array = np.array([])

        # Repeat the RTT measurement 10 times
        for i in range(10):
            # Get pod name of s1-cloud
            command2 = f"kubectl get pods --context {CTX_CLUSTER2} -n edge | awk '/rtt-edge/ {{print $1}}' | head -n 1"
            result2 = subprocess.run(command2, shell=True, capture_output=True, text=True)
            rtt_edge_pod_name = result2.stdout.strip()  # Clean the output

            # Get RTT edge-cloud
            RTT_command = f"kubectl exec -n edge --context {CTX_CLUSTER2} -it {rtt_edge_pod_name} -- bash -c 'curl --head -s -w %{{time_total}} http://rtt-cloud 2>/dev/null | tail -1'"
            RTT_result = subprocess.run(RTT_command, shell=True, capture_output=True, text=True)
            RTT = RTT_result.stdout.strip()  # Clean the output
            try:
                RTT = float(RTT)  
            except ValueError:
                continue
            # Add RTT value to the array
            RTT_array = np.append(RTT_array, RTT)
        threshold = 1.5
        # Filter the values
        for i in range (10):
            std_dev = np.std(RTT_array)
            mean = np.mean(RTT_array)
            RTT_array = [x for x in RTT_array if abs(x - mean) < threshold * std_dev]
        rtt = np.mean(RTT_array)
        RTT = round(float(rtt), 4)
        time.sleep(5)

# Function that save the avg delay in csv file
def save_delay(delay_value):
    with open(f'/home/alex/Downloads/matlab/{FOLDER}/{POSITIONING_TYPE}.csv', 'a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([delay_value])

# Function that save CPU used in edge and cloud clusters in csv file
def save_Rcpu():
    global RCPU_CLOUD
    global RCPU_EDGE
    while True:
        with open(f'/home/alex/Downloads/matlab/{FOLDER}/cpu_cloud_{POSITIONING_TYPE}.csv', 'a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([RCPU_CLOUD])
        with open(f'/home/alex/Downloads/matlab/{FOLDER}/cpu_edge_{POSITIONING_TYPE}.csv', 'a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([RCPU_EDGE])
        time.sleep(1)

# Function that get the cloud-edge traffic and save it in csv file
def get_traffic():
    while True:
        global TRAFFIC
        # total requests that arrive to dst microservice from src microservice + requests that arrive to src microservice from dst microservice
        query = f'(sum((rate(istio_response_bytes_sum{{source_workload=~"s.*[0-12]-edge|istio-ingressgateway", destination_workload=~"s.*[0-12]-cloud", reporter="destination", response_code="200"}}[1m])))+sum((rate(istio_request_bytes_sum{{source_workload=~"s.*[0-12]-edge|istio-ingressgateway", destination_workload=~"s.*[0-12]-cloud", reporter="destination", response_code="200"}}[1m])))) *8 /1000000'
        r1 = prom.custom_query(query=query)
        # Extract values from querie
        if r1:
            for result in r1:
                TRAFFIC = round(float(result["value"][1]), 2)
                #print("traffic=",TRAFFIC,"Mbps")
                with open(f'/home/alex/Downloads/matlab/{FOLDER}/{POSITIONING_TYPE}_traffic.csv', 'a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow([TRAFFIC])
        time.sleep(1)

def main():
    global HPA_STATUS
    global AVG_DELAY
    stabilization_window_seconds = 5  # window in sec

    # Start the thread that checks the HPAs
    thread_hpa = threading.Thread(target=check_hpa) # Create thread
    thread_hpa.daemon = True # Daemonize thread
    thread_hpa.start()

    # Start the thread that checks the RTT cloud-edge
    thread_RTT = threading.Thread(target=get_RTT) # Create thread
    thread_RTT.daemon = True # Daemonize thread
    thread_RTT.start()
    
    # Start the thread that checks the avg delay
    thread_delay = threading.Thread(target=get_avg_delay) # Create thread
    thread_delay.daemon = True # Daemonize thread
    thread_delay.start()

    # Start the thread that checks microservices in edge cluster
    thread_delay = threading.Thread(target=get_app_edge) # Create thread
    thread_delay.daemon = True # Daemonize thread
    thread_delay.start()

    # Start the thread that checks RCPU in clusters 
    thread_delay = threading.Thread(target=get_Rcpu) # Create thread
    thread_delay.daemon = True # Daemonize thread
    thread_delay.start()

    # Start the thread that checks cloud-edge traffic and save it in csv file
    if SAVE_RESULTS == 1:
        thread_delay = threading.Thread(target=get_traffic) # Create thread
        thread_delay.daemon = True # Daemonize thread
        thread_delay.start()
    
    # Start the thread that save Rcpu in csv file
    if SAVE_RESULTS == 1:
        thread_delay = threading.Thread(target=save_Rcpu) # Create thread
        thread_delay.daemon = True # Daemonize thread
        thread_delay.start()
    
    while True:
        if HPA_STATUS == 0:
            print(f"\rCurrent avg_delay: {AVG_DELAY} ms")
            if AVG_DELAY > SLO:
                duration_counter = 0
                while AVG_DELAY > SLO and duration_counter < stabilization_window_seconds and HPA_STATUS == 0:
                    time.sleep(1)
                    if AVG_DELAY > SLO:
                        duration_counter += 1
                    print(f"\r*Current avg_delay: {AVG_DELAY} ms")
                if duration_counter >= stabilization_window_seconds and HPA_STATUS == 0:
                    print(f"\rSLO not satisfied, offloading...")
                    if PLACEMENT_TYPE == "OE_PAMP":
                        OE_PAMP_off()
                    elif PLACEMENT_TYPE == "RANDOM":
                        random_placement()
                    elif PLACEMENT_TYPE == "MFU":
                        mfu_placement()
                    elif PLACEMENT_TYPE == "IA":
                        IA_placement()
            elif AVG_DELAY <= SLO*SLO_MARGIN_UNOFFLOAD:
                duration_counter = 0
                while AVG_DELAY < SLO*SLO_MARGIN_UNOFFLOAD and duration_counter < stabilization_window_seconds and HPA_STATUS == 0:
                    time.sleep(1)
                    print(f"\r**Current avg_delay: {AVG_DELAY} ms")
                    duration_counter += 1
                if AVG_DELAY == 0:
                    continue
                elif duration_counter >= stabilization_window_seconds and HPA_STATUS == 0 and APP_EDGE.any() != 0:
                    print(f"\rSLO not satisfied")
                    if PLACEMENT_TYPE == "OE_PAMP":
                        print(f"\rUnoffloading...")
                        OE_PAMP_unoff()  
            time.sleep(1)
        else:
            print(f"\rHPA running...")
            time.sleep(1)
if __name__ == "__main__":
    main()