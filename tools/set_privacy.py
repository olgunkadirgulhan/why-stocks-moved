"""Verilen videoları gizli (veya --status ile başka) yapar. Silmez; Studio'dan geri açılabilir.
Usage: python tools/set_privacy.py ID [ID ...] [--status private|unlisted|public]"""
import os, sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

args = sys.argv[1:]
status = 'private'
if '--status' in args:
    i = args.index('--status'); status = args[i + 1]; del args[i:i + 2]
ids = [a for x in args for a in x.replace(',', ' ').split()]
env = lambda a, b: os.environ.get(a) or os.environ[b]
creds = Credentials(None, refresh_token=env('YT_REFRESH_TOKEN', 'YOUTUBE_REFRESH_TOKEN'),
                    client_id=env('YT_CLIENT_ID', 'YOUTUBE_CLIENT_ID'),
                    client_secret=env('YT_CLIENT_SECRET', 'YOUTUBE_CLIENT_SECRET'),
                    token_uri='https://oauth2.googleapis.com/token')
yt = build('youtube', 'v3', credentials=creds, cache_discovery=False)
for vid in ids:
    items = yt.videos().list(part='status,snippet', id=vid).execute().get('items', [])
    if not items:
        print(f'✗ {vid}: bulunamadı'); continue
    st = items[0]['status']
    st['privacyStatus'] = status
    st.pop('publishAt', None)
    yt.videos().update(part='status', body={'id': vid, 'status': st}).execute()
    print(f"✓ {vid} -> {status} | {items[0]['snippet']['title'][:70]}")
