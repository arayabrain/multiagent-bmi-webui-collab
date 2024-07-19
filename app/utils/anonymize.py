import os
import re
import hashlib
import json
import sys
import click


def hash_string(username):
    return hashlib.sha256(username.encode()).hexdigest()


def anonymize_session(expid, source_folder, anonymized_folder):
    # Check that source_folder exists
    if not (os.path.exists(source_folder) and os.path.isdir(source_folder)):
        print(f"Experiment data source folder not found: {source_folder}")
        return False

    session_path = os.path.join(source_folder, expid)

    # Check that folder of the expId itself exists
    if not (os.path.exists(session_path) and os.path.isdir(session_path)):
        print(f"Experiment data folder not found: {session_path}")
        return False

    if not os.path.exists(anonymized_folder):
        os.mkdir(anonymized_folder)

    if not os.path.exists(os.path.join(anonymized_folder, expid)):
        os.mkdir(os.path.join(anonymized_folder, expid))

    anon_session_path = os.path.join(anonymized_folder, expid)

    history_file = os.path.join(session_path, 'history.jsonl')
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
    with open(os.path.join(anon_session_path, 'history.jsonl'), 'w') as f:
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
    with open(os.path.join(anon_session_path, 'info.json'), 'w') as f:
        json.dump(info_data, f, indent=4)

    # Copy the rest of the files in session folder to anon-session folder
    for file in os.listdir(session_path):
        if file not in ['history.jsonl', 'info.json']:
            os.system(f'cp {os.path.join(session_path, file)} {os.path.join(anon_session_path, file)}')

    session_users = username_mapping.keys()
    for username in session_users:
        # If user path is anonymized, keep same. If user path still username, rename to anonymized username
        anonymized_username = username_mapping[username]
        user_path = os.path.join(source_folder, username)
        anon_user_path = os.path.join(anonymized_folder, anonymized_username)

        if not os.path.exists(anon_user_path):
            os.mkdir(anon_user_path)

        if not os.path.exists(os.path.join(anon_user_path, expid)):
            os.mkdir(os.path.join(anon_user_path, expid))

        with open(os.path.join(user_path, expid, 'info.json'), 'r') as f:
            user_info_data = json.load(f)

        # Replace instance of username with anonymized username
        if user_info_data['name'] == username:
            user_info_data['name'] = anonymized_username
            user_info_data['user_list'] = [hash_string(user) for user in user_info_data['user_list']]

        with open(os.path.join(anon_user_path, expid, 'info.json'), 'w') as f:
            json.dump(user_info_data, f, indent=4)

        # Copy the rest of the files in session folder to anon-session folder
        for file in os.listdir(os.path.join(user_path, expid)):
            if file not in ['info.json']:
                os.system(f'cp {os.path.join(user_path, expid, file)} {os.path.join(anon_user_path, expid, file)}')


@click.command()
@click.argument('expids', nargs=-1)
@click.option('--source-folder', default='../logs', help='Source folder containing logs.')
@click.option('--anonimized-folder', default='../anon-logs', help='Destination folder for anonymized logs.')
def main(expids, source_folder, anonimized_folder):
    for expid in expids:
        anonymize_session(expid, source_folder, anonimized_folder)


if __name__ == "__main__":
    # usage example
    print('Usage: python anonymize.py <expid1> <expid2> ... --source-folder=<source-folder-path> --anonimized-folder=<anon-folder-path>')
    
    main()
