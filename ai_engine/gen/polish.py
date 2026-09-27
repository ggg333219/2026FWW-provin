"""导出前内容润色：自动把长句改成PPT适合的短文本，去掉冗余口播词"""
from typing import List, Dict

def polish_node(node: dict) -> dict:
    """对单个节点做轻量润色：不改变知识点，只把正文改成适合PPT展示的短句"""
    polished = node.copy()
    # 优先取summary（生产节点默认字段），回退content
    if "summary" in node:
        text = str(node.get("summary") or "")
        target_key = "summary"
    else:
        text = str(node.get("content") or "")
        target_key = "content"
    if text:
        fillers = ["大家好", "我们今天来讲", "众所周知", "废话不多说", "接下来我们"]
        for filler in fillers:
            text = text.replace(filler, "")
        text = text.lstrip("，。、 ").strip()
        polished[target_key] = text
    return polished

def polish_nodes(nodes: List[Dict]) -> List[Dict]:
    """批量润色所有节点"""
    return [polish_node(node) for node in nodes]
