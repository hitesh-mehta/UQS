import requests
import os
from dotenv import load_dotenv

load_dotenv()
url = f"{os.getenv('SUPABASE_URL')}/auth/v1/token?grant_type=password"
headers = {
    'apikey': os.getenv('SUPABASE_ANON_KEY'),
    'Content-Type': 'application/json'
}
data = {
    'email': 'rahul.sharma@brewco.in',
    'password': 'Manager@123'
}
res = requests.post(url, headers=headers, json=data)
print("STATUS:", res.status_code)
print("BODY:", res.text)
