"""
简单后端验证脚本：调用教师端生成音频接口并记录返回的元数据。
用法：
  python scripts/validate_audio_backend.py --backend http://127.0.0.1:8082 --course <courseId> --page 1

结果保存在 validate_audio_response.json
"""
import argparse
import json
import time
from pathlib import Path

import requests


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--backend', required=True)
    p.add_argument('--course', required=True)
    p.add_argument('--page', type=int, default=1)
    p.add_argument('--out', default='validate_audio_response.json')
    args = p.parse_args()

    url = f"{args.backend.rstrip('/')}/api/v1/teacher/coursewares/{args.course}/pages/{args.page}/audio"
    print('POST', url)
    try:
        resp = requests.post(url, json={}, timeout=180)
        print('status', resp.status_code)
        body = resp.json() if resp.headers.get('content-type','').startswith('application/json') else resp.text
    except Exception as e:
        print('请求异常', e)
        body = {'error': str(e)}

    out = {
        'request': {'url': url, 'course': args.course, 'page': args.page, 'ts': int(time.time()*1000)},
        'response': body
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print('写入', args.out)

if __name__ == '__main__':
    main()
