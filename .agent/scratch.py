import os
import re

emoji_pattern = re.compile(r"[\U00010000-\U0010ffff]", flags=re.UNICODE)

for root, _, files in os.walk('templates'):
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                emojis = set(emoji_pattern.findall(content))
                # Also look for basic emojis like 🍿 (which is \U0001f37f)
                if emojis:
                    print(f'{filepath}: {emojis}')
