import sys, json, urllib.request
url='http://127.0.0.1:8000/ask-with-context'
data={"question":"解释牛顿第一定律","current_page":1,"context":""}
b=bytes(json.dumps(data),encoding='utf-8')
req=urllib.request.Request(url,data=b,headers={'Content-Type':'application/json'})
try:
    with urllib.request.urlopen(req,timeout=10) as resp:
        print(resp.status)
        print(resp.read().decode('utf-8'))
except Exception as e:
    print('ERR',e)
    sys.exit(1)
