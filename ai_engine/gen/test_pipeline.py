"""自测脚本：测试新的PPT渲染流水线

运行方式（必须用模块方式运行，否则相对导入失败）：
    python -m ai_engine.gen.test_pipeline
"""
from .svg_renderer import render_node_to_svg
from .quality_checker import run_full_check
from .polish import polish_nodes

# 模拟一个测试节点
test_nodes = [
    {
        "title": "TCP三次握手原理",
        "type": "content",
        "core_points": ["SYN同步报文", "ACK确认报文", "连接建立成功"],
        "content": "大家好，我们今天来讲TCP三次握手。首先客户端发送SYN报文，然后服务端回复SYN+ACK，最后客户端再发ACK，连接就建立成功了。这个过程保证了双方都能正常收发数据。"
    },
    {
        "title": "本节小结",
        "type": "summary",
        "core_points": ["三次握手的作用", "常见报文类型", "常见面试题"]
    }
]

# 生产节点实际用 summary 承载正文（node.py 的规范化字段里没有 content）。
# 润色必须写回 summary，否则会出现"副标题带口播词、正文是干净内容"的同页不一致。
_production_shape_node = {
    "title": "生产形态节点",
    "node_type": "content",
    "summary": "大家好，我们今天来讲生产节点的正文。",
    "content": "干净的正文内容",
}


def test_pipeline():
    print("=== 1. 测试内容润色 ===")
    polished = polish_nodes(test_nodes)
    print(f"润色后正文: {polished[0]['content'][:100]}...")
    assert "大家好" not in polished[0]["content"], "润色未去掉口播词"
    print("✅ 内容润色通过")

    print("\n=== 2. 测试润色写回 summary ===")
    polished_prod = polish_nodes([_production_shape_node])[0]
    assert "大家好" not in polished_prod["summary"], "润色未写回 summary"
    assert polished_prod["content"] == "干净的正文内容", "润色不应改写 content"
    print(f"润色后 summary: {polished_prod['summary']}")
    print("✅ 写回字段正确")

    print("\n=== 3. 测试质量检查 ===")
    check_result = run_full_check(test_nodes)
    print(f"检查结果: {check_result}")
    assert check_result["total_pages"] == 2, "页面数不对"
    print("✅ 质量检查通过")

    print("\n=== 4. 测试SVG渲染 ===")
    svg = render_node_to_svg(test_nodes[0], 1, "default")
    assert "<svg" in svg, "SVG渲染失败"
    assert "TCP三次握手原理" in svg, "SVG里没有标题"
    print(f"生成SVG长度: {len(svg)} 字符")
    print("✅ SVG渲染通过")

    print("\n🎉 所有模块自测通过！流水线工作正常")

if __name__ == "__main__":
    test_pipeline()
