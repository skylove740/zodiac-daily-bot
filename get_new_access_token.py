import os
import json
import base64
import requests

def get_new_access_token():
    data = {
        'client_id': os.environ['YT_CLIENT_ID'],
        'client_secret': os.environ['YT_CLIENT_SECRET'],
        'refresh_token': os.environ['YT_REFRESH_TOKEN'],
        'grant_type': 'refresh_token'
    }

    res = requests.post(os.environ.get('YT_TOKEN_URI', 'https://oauth2.googleapis.com/token'), data=data)
    res.raise_for_status()
    token_data = res.json()
    
    # access_token 및 부가 정보 저장할 dict 생성
    token_info = {
        'access_token': token_data['access_token'],
        'expires_in': token_data['expires_in'],
        'token_type': token_data['token_type'],
        'scope': token_data.get('scope', '')
    }

    # base64 인코딩
    token_json_str = json.dumps(token_info)
    token_b64 = base64.b64encode(token_json_str.encode()).decode()

    return token_b64

if __name__ == "__main__":
    token_b64 = get_new_access_token()
    print("::set-output name=token_b64::" + token_b64)
