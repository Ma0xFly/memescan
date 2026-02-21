import requests
import json

url = "https://api.bscscan.com/api"
params = {
    "module": "contract",
    "action": "getsourcecode",
    "address": "0xb8c77482e45f1f44de1745f52c74426c631bdd52",
    "apikey": "P63YQNN421D9Y533X7V2TMWP1MVTQ497V4"
}
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
try:
    response = requests.get(url, params=params, headers=headers)
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(e)
