system_prompt = """
You are an ai agent whose main goal is to help
users interact with the local filesystem using natural language.
Your main job is to take the prompts that are submitted and
translate them into lower-level commands that a python program will
parse and execute. Respond only with the commands, no extra text.
You are allowed to respond with multiple commands by putting one
command on its own line. 

Here are the available low-level commands that you can respond with:
CREATE_FILE filename - Creates a new file at the specified file path
CREATE_DIRECTORY directory_name - Creates a new empty directory
APPEND_TO_FILE filename content - Adds the specified content to the end of the file
"""

import requests
from pathlib import Path

def create_file(filename):
    """
    Create an empty file at `filename`. Create parent directories as needed.
    If the file already exists, leave it in place.
    """
    path = Path(filename)
    try:
        if path.exists():
            print(f'File already exists: {path}')
            return
        if path.parent != Path('.'):
            path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        print(f'Created file: {path}')
    except Exception as e:
        print(f'Error creating file {filename}: {e}')

def create_dir(dir_name):
    """
    Create a directory (and any needed parents). Does nothing if it already exists.
    """
    path = Path(dir_name)
    try:
        path.mkdir(parents=True, exist_ok=True)
        print(f'Created directory: {path}')
    except Exception as e:
        print(f'Error creating directory {dir_name}: {e}')

def append_to_file(filename, content):
    """
    Append `content` to the file at `filename`. Create parent directories if needed.
    """
    path = Path(filename)
    try:
        if path.parent != Path('.'):
            path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as f:
            f.write(content)
        print(f'Appended to file: {path}')
    except Exception as e:
        print(f'Error appending to file {filename}: {e}')

user_prompt = input("Enter your instructions for the file system agent: ")

messages = [{
    "role": "system",
    "content": system_prompt,
}, {
    "role": "user",
    "content": user_prompt,
}]

print('Processing instructions...')

response = requests.post('http://localhost:11434/api/chat', json={
    "model": "llama4",
    "stream": False,
    "messages": messages,
})

data = response.json()

print('Here are the commands:')
commands_str = data['message']['content']
print(commands_str)

command_lines = commands_str.split('\n')

for line in command_lines:
    parts = line.split(' ')

    if parts[0] == 'CREATE_FILE':
        create_file(parts[1])
    elif parts[0] == 'CREATE_DIRECTORY':
        create_dir(parts[1])
    elif parts[0] == 'APPEND_TO_FILE':
        filename = parts[1]
        content = ' '.join(parts[2:])
        append_to_file(filename, content) 
    else:
        print(f'Unknown command: {line}')
