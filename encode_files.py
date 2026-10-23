import base64, json, os

deploy_dir = 'C:/Users/mm013/AppData/Local/hermes/cache/scratch/telegram_bot_deploy'
files = [
    '.gitignore', 'Dockerfile', 'Procfile', 'README.md', 'README_DEPLOY.md',
    'bot.py', 'deploy.sh', 'docker-compose.yml', 'lms_token.json',
    'requirements.txt', 'run.sh', 'telegram-bot.service',
    'telegram_bot.py', 'telegram_commands.json'
]

result = {}
for f in files:
    filepath = os.path.join(deploy_dir, f)
    if os.path.exists(filepath):
        with open(filepath, 'rb') as fh:
            content = base64.b64encode(fh.read()).decode('utf-8')
        result[f] = content
        print(f'{f}: {len(content)} chars (b64)')
    else:
        print(f'{f}: NOT FOUND')

with open(os.path.join(deploy_dir, 'gh_upload.json'), 'w') as out:
    json.dump(result, out)
print(f'Total files: {len(result)}')
