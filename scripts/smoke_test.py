"""
简单的端到端 smoke 测试脚本（教师侧 + AI 引擎）
用法示例：
  python scripts/smoke_test.py --backend http://127.0.0.1:8082 --ai http://127.0.0.1:8000 --file ./index.html

脚本步骤：
 1) 上传文件到后台 `/api/v1/teacher/coursewares/upload`
 2) 触发后端 AI 生成增强讲稿 `/api/v1/teacher/coursewares/{courseId}/scripts/ai-generate`
 3) 请求生成页面音频 `/api/v1/teacher/coursewares/{courseId}/pages/{pageNum}/audio`
 4) 调用 AI 引擎 `/ask-with-context` 验证问答接口

脚本会记录每步耗时、HTTP 状态码和响应体到 `smoke_test_results.json`。
"""
import argparse
import json
import os
import time
from pathlib import Path

import requests


def now_ts():
    return int(time.time() * 1000)


def timeit(func, *args, **kwargs):
    start = time.time()
    try:
        r = func(*args, **kwargs)
        ok = True
    except Exception as e:
        r = e
        ok = False
    duration = round((time.time() - start) * 1000)
    return ok, r, duration


def post_file_upload(backend_base, file_path):
    url = f"{backend_base.rstrip('/')}/api/v1/teacher/coursewares/upload"
    files = {
        'file': (os.path.basename(file_path), open(file_path, 'rb'))
    }
    data = {'title': os.path.basename(file_path)}
    resp = requests.post(url, files=files, data=data, timeout=180)
    return resp


def post_generate_script(backend_base, course_id, page_num=1):
    url = f"{backend_base.rstrip('/')}/api/v1/teacher/coursewares/{course_id}/scripts/ai-generate"
    resp = requests.post(url, json={'pageNum': page_num, 'mode': 'llm'}, timeout=180)
    return resp


def post_generate_audio(backend_base, course_id, page_num=1):
    url = f"{backend_base.rstrip('/')}/api/v1/teacher/coursewares/{course_id}/pages/{page_num}/audio"
    resp = requests.post(url, json={}, timeout=180)
    return resp


def put_page_nodes(backend_base, course_id, page_num=1, nodes=None):
    url = f"{backend_base.rstrip('/')}/api/v1/teacher/coursewares/{course_id}/pages/{page_num}/nodes"
    payload = nodes or []
    # API expects { "nodes": [ ... ] }
    resp = requests.put(url, json={"nodes": payload}, timeout=180)
    return resp


def post_ai_ask(ai_base, page=1):
    url = f"{ai_base.rstrip('/')}/ask-with-context"
    payload = {
        'question': '请简要说明本页课件的核心教学目标',
        'context': '测试上下文：这是一个用于 smoke 测试的上下文示例',
        'current_page': page
    }
    resp = requests.post(url, json=payload, timeout=60)
    return resp


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--backend', required=True, help='后台服务基地址，例如 http://127.0.0.1:8082')
    p.add_argument('--ai', required=True, help='AI 引擎基地址，例如 http://127.0.0.1:8000')
    p.add_argument('--file', required=True, help='要上传的文件路径（pptx/pdf/html）')
    p.add_argument('--page', type=int, default=1, help='测试的页码，默认 1')
    p.add_argument('--out', default='smoke_test_results.json', help='结果输出文件')
    args = p.parse_args()

    backend = args.backend.rstrip('/')
    ai = args.ai.rstrip('/')
    file_path = Path(args.file)
    page = args.page

    results = {
        'meta': {
            'backend': backend,
            'ai': ai,
            'file': str(file_path),
            'ts': now_ts()
        },
        'steps': []
    }

    if not file_path.exists():
        print('文件不存在：', file_path)
        return

    print('1) 上传文件 ->', backend)
    ok, resp, duration = timeit(post_file_upload, backend, str(file_path))
    step = {'name': 'upload', 'ok': ok, 'duration_ms': duration}
    if ok and isinstance(resp, requests.Response):
        step['status_code'] = resp.status_code
        try:
            step['body'] = resp.json()
        except Exception:
            step['body'] = resp.text[:200]
    else:
        step['error'] = str(resp)
    print('  ', step['ok'], step.get('status_code'), f"{step['duration_ms']}ms")
    results['steps'].append(step)

    course_id = None
    if step.get('status_code') == 200:
        body = step.get('body') or {}
        # 兼容不同后端返回结构：递归查找常见 id 字段
        def find_id(obj):
            if not obj:
                return None
            if isinstance(obj, dict):
                # common keys
                for k in ['courseId', 'course_id', 'id', 'file_id', 'fileId', 'file_id']:
                    if k in obj and obj[k]:
                        return obj[k]
                # check nested data
                for v in obj.values():
                    try:
                        found = find_id(v)
                        if found:
                            return found
                    except Exception:
                        continue
            if isinstance(obj, list):
                for item in obj:
                    found = find_id(item)
                    if found:
                        return found
            # fallback: if it's a non-empty string, return it
            if isinstance(obj, str) and obj.strip():
                return obj.strip()
            return None

        if isinstance(body, dict) or isinstance(body, list) or isinstance(body, str):
            course_id = find_id(body)

    if not course_id:
        print('未能从上传响应中解析到 courseId，退出')
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        return

    print('2) 触发 AI 生成脚本 ->', backend)
    ok, resp, duration = timeit(post_generate_script, backend, course_id, page)
    step = {'name': 'generate_script', 'ok': ok, 'duration_ms': duration}
    if ok and isinstance(resp, requests.Response):
        step['status_code'] = resp.status_code
        try:
            step['body'] = resp.json()
        except Exception:
            step['body'] = resp.text[:200]
    else:
        step['error'] = str(resp)
    print('  ', step['ok'], step.get('status_code'), f"{step['duration_ms']}ms")
    results['steps'].append(step)

    print('3) 请求生成页面音频 ->', backend)
    ok, resp, duration = timeit(post_generate_audio, backend, course_id, page)
    step = {'name': 'generate_audio', 'ok': ok, 'duration_ms': duration}
    if ok and isinstance(resp, requests.Response):
        step['status_code'] = resp.status_code
        try:
            step['body'] = resp.json()
        except Exception:
            step['body'] = resp.text[:200]
    else:
        step['error'] = str(resp)
    print('  ', step['ok'], step.get('status_code'), f"{step['duration_ms']}ms")
    results['steps'].append(step)

    # 如果没有教学节点导致无法生成音频，尝试把脚本生成的文本拆分为最小节点并写回页面节点，再重试一次
    if step.get('status_code') and step.get('status_code') != 200:
        body = step.get('body') or {}
        msg = ''
        if isinstance(body, dict):
            msg = body.get('message') or body.get('msg') or ''
        if '暂无可生成音频' in str(msg) or (isinstance(body, dict) and body.get('code') == 400):
            print('检测到缺少教学节点，准备写入最小节点并重试音频生成')
            # 从生成脚本的返回中尽量获取文本
            gen_step = next((s for s in results['steps'] if s['name'] == 'generate_script'), None)
            gen_text = ''
            if gen_step and isinstance(gen_step.get('body'), dict):
                gen_text = (gen_step['body'].get('data') or {}).get('content') or gen_step['body'].get('data') or ''
            if not isinstance(gen_text, str):
                gen_text = str(gen_text or '')
            if not gen_text:
                gen_text = '示例段落：这是用于生成音频的示例文本。'
            # 简单按句拆分为若干节点
            parts = [p.strip() for p in gen_text.split('\n') if p.strip()]
            if not parts:
                # fallback split by punctuation
                import re
                parts = [s.strip() for s in re.split(r'[。！？\n]', gen_text) if s.strip()]
            nodes_payload = []
            for i, ptext in enumerate(parts[:6]):
                seg_id = f's{i+1}_1'
                node_id = f'p{page}_n{i+1}'
                nodes_payload.append({
                    'nodeId': node_id,
                    'title': f'段落 {i+1}',
                    'scriptText': ptext,
                    'schemaVersion': 2,
                    'estimatedDuration': 30,
                    'sortOrder': i + 1,
                    'scriptSegments': [
                        {
                            'segment_id': seg_id,
                            'start_sec': i * 30,
                            'end_sec': (i + 1) * 30,
                            'text': ptext,
                            'node_ids': [node_id]
                        }
                    ],
                    'knowledgeNodes': [
                        {
                            'node_id': node_id,
                            'title': f'知识点 {i+1}',
                            'prerequisites': [],
                            'coverage_span': [seg_id],
                            'level': 1,
                            'tags': []
                        }
                    ]
                })
            ok2, resp2, dur2 = timeit(put_page_nodes, backend, course_id, page, nodes_payload)
            retry_step = {'name': 'put_nodes', 'ok': ok2, 'duration_ms': dur2}
            if ok2 and isinstance(resp2, requests.Response):
                retry_step['status_code'] = resp2.status_code
                try:
                    retry_step['body'] = resp2.json()
                except Exception:
                    retry_step['body'] = resp2.text[:200]
            else:
                retry_step['error'] = str(resp2)
            results['steps'].append(retry_step)
            # 若写入成功，重试生成音频一次
            if retry_step.get('status_code') == 200:
                print('写入节点成功，重试生成音频')
                ok3, resp3, dur3 = timeit(post_generate_audio, backend, course_id, page)
                retry_audio = {'name': 'generate_audio_retry', 'ok': ok3, 'duration_ms': dur3}
                if ok3 and isinstance(resp3, requests.Response):
                    retry_audio['status_code'] = resp3.status_code
                    try:
                        retry_audio['body'] = resp3.json()
                    except Exception:
                        retry_audio['body'] = resp3.text[:400]
                else:
                    retry_audio['error'] = str(resp3)
                print('  ', retry_audio.get('ok'), retry_audio.get('status_code'), f"{retry_audio['duration_ms']}ms")
                results['steps'].append(retry_audio)

    print('4) 调用 AI 引擎上下文问答 ->', ai)
    ok, resp, duration = timeit(post_ai_ask, ai, page)
    step = {'name': 'ai_ask_with_context', 'ok': ok, 'duration_ms': duration}
    if ok and isinstance(resp, requests.Response):
        step['status_code'] = resp.status_code
        try:
            step['body'] = resp.json()
        except Exception:
            step['body'] = resp.text[:400]
    else:
        step['error'] = str(resp)
    print('  ', step['ok'], step.get('status_code'), f"{step['duration_ms']}ms")
    results['steps'].append(step)

    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print('结果已写入', args.out)


if __name__ == '__main__':
    main()
