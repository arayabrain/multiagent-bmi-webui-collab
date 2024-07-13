import os
import re
import hashlib
import json
import sys

# Function to generate a hashed username
def hash_string(username):
    return hashlib.sha256(username.encode()).hexdigest()

# Function to anonymize session usernames
def anonymize_session(expid):
    # Get session path
    session_path = os.path.join(os.pardir, 'logs', expid)
    print(session_path)

    # Path to the history file
    history_file = os.path.join(session_path, 'history.jsonl')
    # Path to the info file
    info_file = os.path.join(session_path, 'info.json')

    # Dictionary to store original to anonymized username mappings
    username_mapping = {}

    # Read and process the history file
    with open(history_file, 'r') as f:
        history = f.readlines()

    new_lines = []
    for line in history:
        match = re.search(r'"username": "(.*?)"', line)
        if match:
            username = match.group(1)
            if username not in username_mapping:
                username_mapping[username] = hash_string(username)
            anonymized_username = username_mapping[username]
            line = re.sub(r'"username": "(.*?)"', f'"username": "{anonymized_username}"', line)
        new_lines.append(line)

    # Write the new lines back to the history file
    with open(os.path.join(session_path, 'anon-history.jsonl'), 'w') as f:
        f.writelines(new_lines)

    # Read and process the info file
    with open(info_file, 'r') as f:
        info_data = json.load(f)

    # Anonymize usernames in the info file
    if 'usernames' in info_data:
        anonymized_usernames = []
        for username in info_data['usernames']:
            if username not in username_mapping:
                username_mapping[username] = hash_string(username)
            anonymized_usernames.append(username_mapping[username])
        info_data['usernames'] = anonymized_usernames

    # Write the updated info back to the info file
    with open(os.path.join(session_path, 'anon-info.json'), 'w') as f:
        json.dump(info_data, f, indent=4)


    session_users = username_mapping.keys()
    for username in session_users:
        #If user path is anonymized, keep same. If user path still username, rename to anonymized username
        anonymized_username = username_mapping[username]
        user_path = os.path.join(os.pardir, 'logs', anonymized_username, expid)
        if not os.path.exists(user_path):
            #rename directory
            os.rename(os.path.join(os.pardir, 'logs', username, expid), user_path)

        with open(os.path.join(user_path, 'info.json'), 'r') as f:
            user_info_data = json.load(f)
        #replace instance of username with anonymized username
        if user_info_data['name'] == username:
            user_info_data['name'] = anonymized_username
            user_info_data['user_list'] = [anonymized_username if user == username else user for user in user_info_data['user_list']]
        with open(os.path.join(user_path, 'anon-info.json'), 'w') as f:
            json.dump(user_info_data, f, indent=4)



if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python anonymize_session.py <expid1> <expid2> ...")
        sys.exit(1)
    
    expids = sys.argv[1:]
    for expid in expids:
        anonymize_session(expid)
