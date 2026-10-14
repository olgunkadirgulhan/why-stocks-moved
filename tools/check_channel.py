"""Kanal adı/handle/açıklama + son videoların başlık, durum ve açıklamasını yazdırır (sadece okur)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from googleapiclient.discovery import build
from common import yt_creds
yt = build('youtube', 'v3', credentials=yt_creds(), cache_discovery=False)
ch = yt.channels().list(part='snippet,brandingSettings,contentDetails,statistics', mine=True).execute()['items'][0]
print('KANAL:', ch['snippet']['title'], ch['snippet'].get('customUrl'), ch['statistics'])
print('KANAL AÇIKLAMASI:\n' + ch['snippet'].get('description', '') + '\n=====')
up = ch['contentDetails']['relatedPlaylists']['uploads']
ids = [i['contentDetails']['videoId'] for i in yt.playlistItems().list(part='contentDetails', playlistId=up, maxResults=8).execute()['items']]
for v in yt.videos().list(part='snippet,status', id=','.join(ids)).execute()['items']:
    print(f"\n--- {v['id']} [{v['status']['privacyStatus']} {v['status'].get('publishAt','')}] {v['snippet']['title']}")
    print(v['snippet']['description'])
