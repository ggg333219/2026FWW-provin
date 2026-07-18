#!/usr/bin/env python3
"""
API测试脚本 - 测试新实现的知识图谱、通知和任务调度功能
"""

import requests
import json
import time
from datetime import datetime, timedelta

# 配置
BASE_URL = "http://localhost:8080/api/v1"

def test_knowledge_map():
    """测试知识图谱API"""
    print("=== 测试知识图谱API ===")

    # 获取知识图谱
    response = requests.get(f"{BASE_URL}/student/knowledge-map?studentId=test_student_001")
    print(f"获取知识图谱: {response.status_code}")
    if response.status_code == 200:
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))

    # 更新掌握度
    update_data = {
        "studentId": "test_student_001",
        "knowledgePointId": "math_algebra_001",
        "isCorrect": True,
        "responseTime": 5000
    }
    response = requests.post(f"{BASE_URL}/student/knowledge-map/update", json=update_data)
    print(f"更新掌握度: {response.status_code}")
    if response.status_code == 200:
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))

    # 获取薄弱知识点
    response = requests.get(f"{BASE_URL}/student/knowledge-map/weak-points?studentId=test_student_001")
    print(f"获取薄弱知识点: {response.status_code}")
    if response.status_code == 200:
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))

def test_notifications():
    """测试通知API"""
    print("\n=== 测试通知API ===")

    # 创建通知
    notification_data = {
        "userId": 1,
        "title": "学习提醒",
        "content": "您有新的复习任务待完成",
        "type": "review_reminder",
        "channels": ["app", "email"],
        "scheduledAt": int((datetime.now() + timedelta(minutes=5)).timestamp())
    }
    response = requests.post(f"{BASE_URL}/notifications", json=notification_data)
    print(f"创建通知: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        notification_id = result.get("data", {}).get("ID")

        # 获取通知列表
        response = requests.get(f"{BASE_URL}/notifications?userId=1")
        print(f"获取通知列表: {response.status_code}")

        # 标记为已读
        if notification_id:
            response = requests.put(f"{BASE_URL}/notifications/{notification_id}/read")
            print(f"标记已读: {response.status_code}")

def test_task_scheduler():
    """测试任务调度API"""
    print("\n=== 测试任务调度API ===")

    # 创建定时任务
    task_data = {
        "userId": 1,
        "taskType": "review_plan",
        "taskData": json.dumps({"courseId": "course_001", "reviewType": "spaced_repetition"}),
        "cronExpr": "0 9 * * *",  # 每天早上9点
        "description": "每日复习计划生成",
        "maxRetries": 3,
        "priority": 1
    }
    response = requests.post(f"{BASE_URL}/tasks/scheduled", json=task_data)
    print(f"创建定时任务: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        task_id = result.get("data", {}).get("ID")

        # 获取任务列表
        response = requests.get(f"{BASE_URL}/tasks/scheduled?userId=1")
        print(f"获取任务列表: {response.status_code}")

        # 立即执行任务
        if task_id:
            response = requests.post(f"{BASE_URL}/tasks/scheduled/{task_id}/execute")
            print(f"立即执行任务: {response.status_code}")

def main():
    """主测试函数"""
    print("开始API功能测试...")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"目标服务器: {BASE_URL}")

    try:
        # 测试健康检查
        response = requests.get("http://localhost:8080/health")
        if response.status_code != 200:
            print("❌ 服务器未启动或健康检查失败")
            return

        print("✅ 服务器运行正常")

        # 执行各项测试
        test_knowledge_map()
        test_notifications()
        test_task_scheduler()

        print("\n🎉 所有API测试完成！")

    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务器，请确保后端服务已启动")
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {e}")

if __name__ == "__main__":
    main()