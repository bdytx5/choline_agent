# this will read machine params like GPU and Storage params from the choline json, and then ask u to select an instance 
# then it will use the software env info in the choline.json file to create an onstart script to set up the environment 
## then it will monitor the status of that machine and alert u if it fails 
import os
import sys
import json
import subprocess
import time
import threading
import argparse
import argparse
import os
import subprocess
import json
import torch
import re 
import yaml 
import os
import paramiko
import scp 
from scp import SCPClient
from fnmatch import fnmatch
import traceback
import yaml 

import re


##### for choline Chat, need to get an arg corresponding the the llm, and use that to signify which python script to run
def write_runtime_yaml():
    """
    Write choline_runtime.yaml to .choline/ for SCP.
    Single file containing all launch-time dynamic config:
    API_KEYS, repo config, claude_prompt, claude_model, etc.
    """
    choline_yaml = os.path.join(os.getcwd(), "choline.yaml")
    if not os.path.exists(choline_yaml):
        return
    with open(choline_yaml, 'r') as f:
        data = yaml.safe_load(f) or {}

    runtime = {}

    # API keys
    api_keys = dict(data.get('API_KEYS', {}))
    api_keys.pop('CLAUDE_CODE_OAUTH_TOKEN', None)
    if api_keys:
        runtime['API_KEYS'] = api_keys

    # Repo config
    git_username = data.get('git_username', '')
    git_token = data.get('git_token', '')
    repo_name = data.get('repo_name', '')
    if git_username:
        runtime['git_username'] = git_username
    if git_token:
        runtime['git_token'] = git_token
    if repo_name:
        runtime['repo_name'] = repo_name
    if git_username and git_token and repo_name:
        runtime['clone_url'] = f"https://{git_username}:{git_token}@github.com/{git_username}/{repo_name}.git"

    # Claude prompt
    claude_prompt = data.get('claude_prompt', '')
    if claude_prompt:
        runtime['claude_prompt'] = claude_prompt

    # Claude model
    claude_model = data.get('claude_model', '')
    if claude_model:
        runtime['claude_model'] = claude_model

    # Vast.ai API key — read from ~/.vast_api_key so instances can self-destroy
    try:
        vast_key_path = os.path.expanduser("~/.vast_api_key")
        if os.path.exists(vast_key_path):
            with open(vast_key_path) as vf:
                vast_key = vf.read().strip()
            if vast_key:
                runtime['vastai_api_key'] = vast_key
    except Exception:
        pass

    if not runtime:
        return

    choline_dir = os.path.join(os.getcwd(), ".choline")
    os.makedirs(choline_dir, exist_ok=True)
    runtime_path = os.path.join(choline_dir, "choline_runtime.json")
    with open(runtime_path, 'w') as f:
        json.dump(runtime, f, indent=2)


def read_setup_from_choline_yaml_and_write_sh_to_disk():
    ### todo -> need to also write the instances
    choline_data = get_choline_yaml_data()

    setup_script = choline_data.get('setup_script', '')
    cwd = os.getcwd()

    setup_script_path = os.path.join(cwd, ".choline", "choline_setup.sh")

    # Save the script to a file
    with open(setup_script_path, "w") as f:
        f.write(setup_script)

    # Write runtime yaml from choline.yaml at launch time
    write_runtime_yaml()

    # Copy helper scripts into .choline/
    import shutil
    pkg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
    for script_name in ("parse_runtime.py", "format_session.py"):
        src = os.path.join(pkg_dir, script_name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(cwd, ".choline", script_name))

    return setup_script_path




def pretty_print_offer(offer, index):
    # print(offer)
    print(f"########### VASTAI OFFERS {index + 1} ###########")
    print(f"GPU MODEL: {offer['gpu_name']}")
    print(f"VRAM: {offer['gpu_ram']}")
    print(f"cpu RAM: {offer['cpu_ram']}")
    print(f"Cost per hour: {offer['dph_base']}")
    print(f"Internet download speed: {offer['inet_down']}")
    print(f"Internet upload speed: {offer['inet_up']}")
    print(f"cuda: {offer['cuda_max_good']}")
    print(f"DL Performance: {offer['dlperf']}")
    print(f"Reliability: {offer['reliability2']}")
    print(f"Storage cost: {offer['storage_cost']}")
    print(f"Internet download cost: {offer['inet_down_cost']}")
    print(f"Internet upload cost: {offer['inet_up_cost']}")
    print("#######################################\n\n")


def get_choline_yaml_data():
    with open('./choline.yaml', 'r') as yaml_file:
        data = yaml.safe_load(yaml_file)
    
    return data



def get_choline_json_data():
    with open('./choline.json', 'r') as f:
        return json.load(f)











def ssh_copy_directory(scp, ssh, local_path, remote_base_path):
    # ignore_patterns = read_cholineignore()
    ignore_patterns = []
    cwd = os.getcwd()
    file_count = 0
    for root, dirs, files in os.walk(local_path):
        for file_name in files:
            local_file = os.path.join(root, file_name)
            relative_path = os.path.relpath(local_file, cwd)
            # if should_ignore(relative_path, ignore_patterns):
            #     continue
            remote_file = os.path.join(remote_base_path, relative_path).replace('\\', '/')
            remote_dir = os.path.dirname(remote_file)

            stdin, stdout, stderr = ssh.exec_command(f"mkdir -p {remote_dir}")
            stdout.read()
            print(f"Copying {relative_path} to remote...", flush=True)
            scp.put(local_file, remote_file)
            file_count += 1
    print(f"Finished copying {file_count} files", flush=True)



def ssh_copy(username, host, port, src, dest):
    print(f"Starting SSH copy from {src} to {dest}...", flush=True)
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.WarningPolicy)
    client.connect(host, port=port, username=username,)
    with SCPClient(client.get_transport()) as scp:
        if os.path.isdir(src):
            print(f"Copying directory {src}...", flush=True)
            ssh_copy_directory(scp, client, src, dest)
        else:
            relative_path = os.path.relpath(src, os.getcwd())
            remote_file = os.path.join(dest, relative_path)
            print(f"Copying file {relative_path} to remote...", flush=True)
            scp.put(src, remote_file)
    client.close()
    print("SSH copy completed", flush=True)




def generate_vast_onstart_script():
    # Create .choline directory if it doesn't exist
    choline_dir = os.path.join(os.getcwd(), ".choline")
    if not os.path.exists(choline_dir):
        os.makedirs(choline_dir)

    script_lines = [
        "#!/bin/bash",
        "mkdir -p ~/.choline",  # Create the directory if it doesn't exist
        "echo '0' > ~/choline.txt",
        "while [ ! -f ~/.choline/choline_setup.sh ]; do",
        "  sleep 1",
        "done",
        "sleep 5",  # Allow time for the full script to arrive
        "echo 'running setup script' > ~/choline.txt",
        ". ~/.choline/choline_setup.sh >> ~/.choline/choline_setup_log.txt 2>&1",
        # "sh -x ~/.choline/choline_setup.sh >> ~/.choline/choline_setup_log.txt 2>&1"  # Run the script from its expected directory
    ]

    script_content = "\n".join(script_lines)
    setup_script_path = os.path.join(choline_dir, "choline_onstart.sh")

    with open(setup_script_path, "w") as f:
        f.write(script_content)

    return setup_script_path



def search_offers(additional_query=""):
    # query = f"cuda_vers == {cuda_version}"
    query = f""
    if additional_query:
        query = f"{query} {additional_query}"

    command = ["vastai", "search", "offers", "--raw", query]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout_str = result.stdout.decode()
    if result.returncode != 0 or "failed with error" in stdout_str:
        print("Error in search:", stdout_str or result.stderr.decode())
        return []

    try:
        offers = json.loads(stdout_str)
    except json.JSONDecodeError:
        print("Error parsing search results:", stdout_str)
        return []
    return offers






def custom_sort_key(offer, expected_storage_gb, expected_runtime_hr, expected_upload_gb=1.0):
    dph = offer['dph_base']
    storage_cost_per_hr = (offer['storage_cost'] / (30 * 24)) * expected_storage_gb
    total_storage_cost = storage_cost_per_hr * expected_runtime_hr
    download_cost = expected_storage_gb * offer['inet_down_cost']
    upload_cost = expected_upload_gb * offer['inet_up_cost']
    total_cost = (dph + storage_cost_per_hr) * expected_runtime_hr + download_cost + upload_cost
    print(total_cost)
    return total_cost




def sort_offers_by_custom_criteria(offers, expected_storage_gb, expected_runtime_hr):
    return sorted(offers, key=lambda x: custom_sort_key(x, expected_storage_gb, expected_runtime_hr))


def create_instance(instance_id, options):
    command = ["vastai", "create", "instance", str(instance_id)] + options
    print(command)
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print("res {}".format(result))

    stdout_str = result.stdout.decode()

    if result.returncode != 0 or "failed with error" in stdout_str:
        print("Error in instance creation:", stdout_str or result.stderr.decode())
        return None

    try:
        match = re.search(r"'new_contract': (\d+)", stdout_str)
        if match:
            new_contract = match.group(1)
            print(f"New contract ID: {new_contract}")
        else:
            print("Failed to find new contract ID.")
            return None
    except Exception as e:
        print(f"Error while parsing: {e}")
        return None

    print("Instance created successfully.")
    return new_contract


### this previously used to use pass the vast id 
####### we are modifying to simply pass an ssh address 

# def check_for_choline_txt(vastai_id):
#     result = subprocess.run(f"vastai copy {vastai_id}:/root/choline.txt ~/.choline", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL)
#     print(str(result))
    
#     if result.returncode != 0 or "Invalid src_id" in result.stdout or "Invalid src_full_path" in result.stdout:
#         print("Machine not yet operational. Waiting...")
#         return False

#     print(f"Detected Operational Machine {vastai_id}.")
#     return True





def check_for_choline_txt(vastai_id):
    from choline.commands.monitor_and_setup_machine import check_for_choline_txt as _check
    return _check(vastai_id)

# def check_remote_file_exists(username, host, port, remote_path):

#     try:
#         client = paramiko.SSHClient()
#         client.load_system_host_keys()
#         client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
#         client.connect(host, port=port, username=username)
                
#         # Command to check if the file exists
#         stdin, stdout, stderr = client.exec_command(f"test -f {remote_path} && echo 'exists' || echo 'not exists'")
#         result = stdout.read().decode().strip()
        
#         # Close the client connection
#         client.close()

#         # Return True if file exists, False otherwise
#         return result == "exists"
#     except Exception as e:
                                
#         print(f"Error checking file existence, waiting : {str(e)}")
#         # Close the client connection in case of an error
#         time.sleep(6)
#         client.close()
#         return False
    


def get_ssh_details(vastai_id):
    result = subprocess.run(f"vastai ssh-url {vastai_id}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    ssh_url = result.stdout.strip()
    if ssh_url.startswith('ssh://'):
        ssh_url = ssh_url[6:]
    username, rest = ssh_url.split('@')
    host, port = rest.split(':')
    return username, host, port

##### T0d0 - change the id to ssh address
def run_monitor_instance_script_vast(instance_id, max_checks=300):
    print(f"DEBUG: run_monitor_instance_script_vast() STARTING with instance_id={instance_id}", flush=True)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    monitor_script_path = os.path.join(script_dir, "monitor_and_setup_machine.py")
    print("waiting 25 seconds for machine startup...", flush=True)
    time.sleep(25)
    checks = 0
    # wait patiently
    while checks < max_checks:
        try:
            # u,h,p = get_ssh_details(instance_id)
            # if check_remote_file_exists(u, h, p, "/root/choline.txt"):
            if check_for_choline_txt(instance_id): # signifys machine is operational
                u,h,p = get_ssh_details(instance_id)
                uhp_str = "{},{},{}".format(u,h,p) # pass to monitor
                print("Sending Upload Locations", flush=True)
                subprocess.Popen(["sudo", "-E", sys.executable, "-u", monitor_script_path, "--uhp", uhp_str, "--max_checks", str(max_checks)])
                print("Data sync complete", flush=True)
                return True

            print("waiting to try again", flush=True)
            time.sleep(6)
            checks += 1
        except Exception as e:
            time.sleep(5)
            import traceback


            print("Error setting up machine. This may not be severe, and we will retry momentarily", flush=True)
            traceback.print_exc()

            if checks >= max_checks:
                print("failed to setup machine. We reccomend you try to launch a different machine, as this is likely an issue with the machine", flush=True)
                return False 



    




# def main(max_price=0):
#     # choline_data = get_choline_json_data()
#     choline_data = get_choline_yaml_data()

#     hardware_filters = choline_data.get('hardware_filters', {})
#     cpu_ram_str = hardware_filters.get('cpu_ram', '')
#     print("CP RAM {}".format(cpu_ram_str))
#     gpu_name = hardware_filters.get('gpu_name', '')
#     disk_space_str = hardware_filters.get('disk_space', '')
#     image = choline_data.get('image', 'python:3.8')
#     num_gpus = choline_data.get('num_gpus', '1')
#     print(num_gpus + "##########"*10)
#     startup_script_path = generate_vast_onstart_script()

#     read_setup_from_choline_yaml_and_write_sh_to_disk()

#     # Extract operator and value from the disk_space string
#     match = re.match(r"([<>!=]+)(\d+)", cpu_ram_str)
#     if match:
#         cpu_ram_operator, cpu_ram_value = match.groups()
#         cpu_ram_value = int(cpu_ram_value)
#     else:
#         print("Invalid disk_space string in JSON. Using default values.")
#         return 
#     # Extract operator and value from the disk_space string
#     match = re.match(r"([<>!=]+)(\d+)", disk_space_str)
#     if match:
#         disk_space_operator, disk_space_value = match.groups()
#         disk_space_value = int(disk_space_value)
#     else:
#         print("Invalid disk_space string in JSON. Using default values.")
#         return 

#     if gpu_name.lower() != 'any':

#         query = f"gpu_name={gpu_name} num_gpus>={num_gpus} disk_space {disk_space_operator} {disk_space_value} cpu_ram > {cpu_ram_value}"
#     else:
#         query = f"disk_space {disk_space_operator} {disk_space_value} cpu_ram > {cpu_ram_value}"

#     print("QUERY {}".format(query))
#     offers = search_offers(query)
#     exp_storage = disk_space_value

#     offers = sort_offers_by_custom_criteria(offers, expected_storage_gb=exp_storage, expected_runtime_hr=2)
#     choice = 0 
#     print("mx price: {}".format(max_price))
#     if offers:
        
#         res = 'y'
#         if not max_price:
#             print("Five cheapest offers:------")
#             for i, offer in enumerate(offers[:20]):
#                 pretty_print_offer(offer, i)
#                 # print(offer)

#             choice = int(input("Select an offer by entering its number (1-5): ")) - 1



#             selected_offer = offers[choice]
#             pretty_print_offer(selected_offer, choice)

#             confirmation = input("Would you like to proceed? (y/n): ")
#             res = confirmation.lower()
#         else:##### t0d0 add more filtering for reliability etc etc 
#             selected_offer = offers[0]


#         if res == 'y' or max_price:
#             instance_id = selected_offer["id"]
#             options = ["--image", image, "--disk", str(disk_space_value), "--onstart", startup_script_path, "--env", "-e TZ=PDT -e XNAME=XX4 -p 22:22 -p 5000:5000"]
#             contract_id = create_instance(instance_id, options)
 
#             print(int(contract_id))
#             run_monitor_instance_script_vast(instance_id=int(contract_id))
#             print(f"Instance creation request complete. Now setting up your instance with id {instance_id}. Run 'choline status 'instance id'' to check the logs for your setup.")
#         else:
#             print("Operation canceled.")
#     else:
#         print("No suitable offers found.")

def mainf(max_price=0, exclude_instances=[]):
    
    # choline_data = get_choline_json_data()
    choline_data = get_choline_yaml_data()

    hardware_filters = choline_data.get('hardware_filters', {})
    cpu_ram_str = hardware_filters.get('cpu_ram', '')
    print("CP RAM {}".format(cpu_ram_str))
    gpu_name = hardware_filters.get('gpu_name', '')
    disk_space_str = hardware_filters.get('disk_space', '')
    image = choline_data.get('image', 'python:3.8')
    num_gpus = choline_data.get('num_gpus', '1')
    print(num_gpus + "##########"*10)
    startup_script_path = generate_vast_onstart_script()

    read_setup_from_choline_yaml_and_write_sh_to_disk()

    # Extract operator and value from the disk_space string
    match = re.match(r"([<>!=]+)(\d+)", cpu_ram_str)
    if match:
        cpu_ram_operator, cpu_ram_value = match.groups()
        cpu_ram_value = int(cpu_ram_value)
    else:
        print("Invalid disk_space string in JSON. Using default values.")
        return 
    # Extract operator and value from the disk_space string
    match = re.match(r"([<>!=]+)(\d+)", disk_space_str)
    if match:
        disk_space_operator, disk_space_value = match.groups()
        disk_space_value = int(disk_space_value)
    else:
        print("Invalid disk_space string in JSON. Using default values.")
        return 

    if gpu_name.lower() != 'any':
        query = f"gpu_name={gpu_name} num_gpus>={num_gpus} disk_space {disk_space_operator} {disk_space_value} cpu_ram > {cpu_ram_value}"
    else:
        query = f"disk_space {disk_space_operator} {disk_space_value} cpu_ram > {cpu_ram_value}"

    print("QUERY {}".format(query))
    offers = search_offers(query)
    exp_storage = disk_space_value

    offers = sort_offers_by_custom_criteria(offers, expected_storage_gb=exp_storage, expected_runtime_hr=2)
    choice = 0 
    print("mx price: {}".format(max_price))
    if offers:
        print("found offers")
        res = 'y'
        if not max_price:
            print("Five cheapest offers:------")
            for i, offer in enumerate(offers[:20]):
                pretty_print_offer(offer, i)
            
            choice = int(input("Select an offer by entering its number (1-5): ")) - 1
            selected_offer = offers[choice]
            pretty_print_offer(selected_offer, choice)
            confirmation = input("Would you like to proceed? (y/n): ")
            res = confirmation.lower()
        else:
            selected_offer = offers[3] # cheapest offer mostly sucks 
            if selected_offer['dph_base'] > max_price:
                res = 'n'
                max_price = 0 

        if res == 'y' or max_price:
            instance_id = selected_offer["id"]
            # yield instance_id  # Yield instance_id here
            options = ["--image", image, "--disk", str(disk_space_value), "--onstart", startup_script_path, "--env", "-e TZ=PDT -e XNAME=XX4 -p 22:22 -p 5000:5000"]
            contract_id = create_instance(instance_id, options)
            if contract_id is None:
                yield -1
                print("Instance creation failed.")
                return

            # print(int(contract_id))

            startup_res = run_monitor_instance_script_vast(instance_id=int(contract_id))
            if startup_res: 
                yield str(instance_id)  + "_" + str(contract_id)  # Yield instance_id here
                print(f"Instance creation request complete. Now setting up your instance with id {instance_id}. Run 'choline status 'instance id'' to check the logs for your setup.")
            else: 
                yield -1 # eg failed startuo =
                print(f"Instance creation request failed.")
                
        else:
            print("Operation canceled.")
            yield 0 # no offers found 
    else:
        print("No suitable offers found.")
        yield 0 # no offers found 

# def main_launch(max_price=None, verbose=False):
#     choline_data = get_choline_yaml_data()

#     hardware_filters = choline_data.get('hardware_filters', {})
#     cpu_ram_str = hardware_filters.get('cpu_ram', '')
#     if verbose:
#         print(f"CP RAM {cpu_ram_str}")
#     gpu_name = hardware_filters.get('gpu_name', '')
#     disk_space_str = hardware_filters.get('disk_space', '')
#     image = choline_data.get('image', 'python:3.8')
#     num_gpus = choline_data.get('num_gpus', '1')
#     if verbose:
#         print(f"{num_gpus} ##########")
#     startup_script_path = generate_vast_onstart_script()

#     read_setup_from_choline_yaml_and_write_sh_to_disk()

#     match = re.match(r"([<>!=]+)(\d+)", cpu_ram_str)
#     if match:
#         cpu_ram_operator, cpu_ram_value = match.groups()
#         cpu_ram_value = int(cpu_ram_value)
#     else:
#         if verbose:
#             print("Invalid disk_space string in JSON. Using default values.")
#         return
#     match = re.match(r"([<>!=]+)(\d+)", disk_space_str)
#     if match:
#         disk_space_operator, disk_space_value = match.groups()
#         disk_space_value = int(disk_space_value)
#     else:
#         if verbose:
#             print("Invalid disk_space string in JSON. Using default values.")
#         return

#     if gpu_name.lower() != 'any':
#         query = f"gpu_name={gpu_name} num_gpus>={num_gpus} disk_space {disk_space_operator} {disk_space_value} cpu_ram > {cpu_ram_value}"
#     else:
#         query = f"disk_space {disk_space_operator} {disk_space_value} cpu_ram > {cpu_ram_value}"

#     if verbose:
#         print(f"QUERY {query}")
#     offers = search_offers(query)
#     exp_storage = disk_space_value

#     offers = sort_offers_by_custom_criteria(offers, expected_storage_gb=exp_storage, expected_runtime_hr=2)

#     if offers:
#         valid_offers = [offer for offer in offers if max_price is None or offer['dph_base'] <= max_price]
#         if valid_offers:
#             selected_offer = valid_offers[0]
#             if verbose:
#                 pretty_print_offer(selected_offer, 0)

#             instance_id = selected_offer["id"]
#             options = ["--image", image, "--disk", str(disk_space_value), "--onstart", startup_script_path, "--env", "-e TZ=PDT -e XNAME=XX4 -p 22:22 -p 5000:5000"]
#             contract_id = create_instance(instance_id, options)

#             if verbose:
#                 print(int(contract_id))
#             run_monitor_instance_script_vast(instance_id=int(contract_id))
#             if verbose:
#                 print(f"Instance creation request complete. Now setting up your instance with id {instance_id}. Run 'choline status {instance_id}' to check the logs for your setup.")
#         else:
#             if verbose:
#                 print(f"No offers within the price range of {max_price}.")
#     else:
#         if verbose:
#             print("No suitable offers found.")




def old_main():
    print("DEBUG: old_main() STARTING", flush=True)
    print("DEBUG: old_main() STARTING", flush=True)

    print("DEBUG: old_main() STARTING", flush=True)

    print("DEBUG: old_main() STARTING", flush=True)

    print("DEBUG: old_main() STARTING", flush=True)

    # choline_data = get_choline_json_data()
    choline_data = get_choline_yaml_data()

    hardware_filters = choline_data.get('hardware_filters', {})
    cpu_ram_str = hardware_filters.get('cpu_ram', '')
    print("CP RAM {}".format(cpu_ram_str))
    gpu_name = hardware_filters.get('gpu_name', '')
    disk_space_str = hardware_filters.get('disk_space', '')
    image = choline_data.get('image', 'python:3.8')
    num_gpus = choline_data.get('num_gpus', '1')
    print(num_gpus + "##########"*10)
    startup_script_path = generate_vast_onstart_script()

    read_setup_from_choline_yaml_and_write_sh_to_disk()

    # Extract operator and value from the disk_space string
    match = re.match(r"([<>!=]+)(\d+)", cpu_ram_str)
    if match:
        cpu_ram_operator, cpu_ram_value = match.groups()
        cpu_ram_value = int(cpu_ram_value)
    else:
        print("Invalid disk_space string in JSON. Using default values.")
        return 
    # Extract operator and value from the disk_space string
    match = re.match(r"([<>!=]+)(\d+)", disk_space_str)
    if match:
        disk_space_operator, disk_space_value = match.groups()
        disk_space_value = int(disk_space_value)
    else:
        print("Invalid disk_space string in JSON. Using default values.")
        return 

    if gpu_name.lower() != 'any':
        print("############"*10)
        print("############"*10)
        print("############"*10)
        print("############"*10)
        print("############"*10)
        print("############"*10)
        print("############"*10)
        query = f"gpu_name={gpu_name} num_gpus>={num_gpus} disk_space {disk_space_operator} {disk_space_value} cpu_ram > {cpu_ram_value}"
    else:
        query = f"disk_space {disk_space_operator} {disk_space_value} cpu_ram > {cpu_ram_value}"

    print("QUERY {}".format(query))
    offers = search_offers(query)
    exp_storage = disk_space_value

    offers = sort_offers_by_custom_criteria(offers, expected_storage_gb=exp_storage, expected_runtime_hr=2)

    if offers:
        print("Five cheapest offers:------")
        for i, offer in enumerate(offers[:20]):
            pretty_print_offer(offer, i)
            # print(offer)

        raw = input("Select offers to launch (e.g. '1' or '1,3,5'): ").strip()
        try:
            choices = [int(x.strip()) - 1 for x in raw.split(",")]
        except ValueError:
            print("Invalid selection.")
            return

        selected_offers = []
        for c in choices:
            if 0 <= c < len(offers):
                pretty_print_offer(offers[c], c)
                selected_offers.append(offers[c])
            else:
                print(f"Offer {c+1} out of range, skipping.")

        if not selected_offers:
            print("No valid offers selected.")
            return

        confirmation = input("Would you like to proceed? (y/n): ")
        if confirmation.lower() != 'y':
            print("Operation canceled.")
            return

        options_base = ["--image", image, "--disk", str(disk_space_value), "--onstart", startup_script_path, "--env", "-e TZ=PDT -e XNAME=XX4 -p 22:22 -p 5000:5000"]

        # launch all N instances, race them — first to come up wins, rest get destroyed
        launched = []  # list of contract_id ints
        for offer in selected_offers:
            cid = create_instance(offer["id"], options_base)
            if cid is not None:
                launched.append(int(cid))
                print(f"Launched contract {cid} (offer {offer['id']})")
            else:
                print(f"Failed to launch offer {offer['id']}, skipping.")

        if not launched:
            print("All instance launches failed.")
            return

        if len(launched) == 1:
            run_monitor_instance_script_vast(instance_id=launched[0])
            print(f"Instance {launched[0]} is ready.")
            return

        print(f"Racing {len(launched)} instances: {launched} — first to come up wins.")

        winner = [None]
        winner_lock = threading.Lock()

        def race_instance(contract_id, others):
            # keep retrying until this instance comes up or another wins
            while True:
                if winner[0] is not None:
                    return  # someone else already won, bail out
                if check_for_choline_txt(contract_id):
                    break
                print(f"Instance {contract_id} not up yet, retrying in 10s...", flush=True)
                time.sleep(10)

            with winner_lock:
                if winner[0] is not None:
                    # someone else already won, destroy this one
                    print(f"Instance {contract_id} came up but {winner[0]} already won — destroying {contract_id}.")
                    subprocess.run(["vastai", "destroy", "instance", str(contract_id)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    return
                winner[0] = contract_id

            # destroy all losers
            for loser in others:
                if loser != contract_id:
                    print(f"Destroying losing instance {loser}.", flush=True)
                    subprocess.run(["vastai", "destroy", "instance", str(loser)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            print(f"Winner: instance {contract_id}. Starting sync.", flush=True)
            run_monitor_instance_script_vast(instance_id=contract_id)
            print(f"Instance {contract_id} is ready.")

        threads = []
        for cid in launched:
            t = threading.Thread(target=race_instance, args=(cid, launched), daemon=True)
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

    else:
        print("No suitable offers found.")

def idk():
    print('idk')
# def bid(mx_price):
#     main(max_price=mx_price)

def launch_by_machine_id(machine_id):
    """Find offers for a specific machine_id, preview, confirm, and launch."""
    choline_data = get_choline_yaml_data()
    hardware_filters = choline_data.get('hardware_filters', {})
    disk_space_str = hardware_filters.get('disk_space', '>50')
    image = choline_data.get('image', 'ubuntu:20.04')
    match = re.match(r"([<>!=]+)(\d+)", disk_space_str)
    disk_space_value = int(match.group(2)) if match else 50

    startup_script_path = generate_vast_onstart_script()
    read_setup_from_choline_yaml_and_write_sh_to_disk()

    all_offers = search_offers(f"machine_id={machine_id}")
    if not all_offers:
        print(f"No offers found for machine_id {machine_id}.")
        return

    offer = all_offers[0]
    pretty_print_offer(offer, 0)

    confirm = input("Launch this instance? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Canceled.")
        return

    options = ["--image", image, "--disk", str(disk_space_value), "--onstart", startup_script_path, "--env", "-e TZ=PDT -e XNAME=XX4 -p 22:22 -p 5000:5000"]
    contract_id = create_instance(offer["id"], options)
    if contract_id is None:
        print("Instance creation failed.")
        return

    print(f"Contract ID: {contract_id}. Waiting for machine to come up...")
    run_monitor_instance_script_vast(instance_id=int(contract_id))
    print(f"Instance {contract_id} is ready.")


def run(mx_price=0):
    machine_id = sys.argv[2] if len(sys.argv) > 2 else None
    if machine_id and machine_id.isdigit():
        launch_by_machine_id(machine_id)
    else:
        old_main()