import sys
import re

ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

interesting_words = ['close', 'error', 'drop', 'reject', 'app_info', 'request', 'msgpack']
ignore_words = ['cranelift', 'webrtc', 'gossip', 'metrics', 'sqlite', 'tx5', 'rustls', 'lair', 'p2p']

with open('/tmp/hc_trace.log', 'r') as f:
    for line in f:
        clean_line = ansi_escape.sub('', line)
        lower_line = clean_line.lower()
        if any(w in lower_line for w in interesting_words):
            if not any(ig in lower_line for ig in ignore_words):
                print(clean_line.strip())
