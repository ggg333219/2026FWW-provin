import json
from urllib import request

url = 'http://127.0.0.1:8000/intent/extract?mode=llm'

cases = [
    {
        'session_id': 'case1',
        'messages': [{'role': 'teacher', 'content': '我要一份35分钟的算法讲解，面向高中生，希望包含互动练习和习题'}],
    },
    {
        'session_id': 'case2',
        'messages': [{'role': 'teacher', 'content': '请帮我生成一份50分钟的函数式编程讲稿，面向大二计算机学生，包含案例分析和讨论环节'}],
    },
    {
        'session_id': 'case3',
        'messages': [{'role': 'teacher', 'content': '我需要一份30分钟的语文阅读练习课件，面向初三学生，重点讲解古诗鉴赏，并带小测试'}],
    },
    {
        'session_id': 'case4',
        'messages': [{'role': 'teacher', 'content': '帮我准备一节40分钟的高中物理实验测验，包含实验原理、练习题和互动问答'}],
    },
    {
        'session_id': 'case5',
        'messages': [{'role': 'teacher', 'content': '我要一份45分钟的思维导图课件，面向历史老师使用，包含知识点梳理和课堂活动'}],
    },
]

for case in cases:
    data = json.dumps(case).encode('utf-8')
    req = request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    print('\n===', case['session_id'], '===')
    try:
        print(request.urlopen(req).read().decode())
    except Exception as e:
        print('ERROR:', e)
