#!/usr/bin/env python3
"""
全链路集成测试 — 演示 S3 课件生成 + S4 个性化满足完整流程

功能：
  1. Markdown → 大纲 (OutlineBuilder)
  2. 大纲 → 节点讲稿 (NodeGenerator)
  3. 版本快照 (VersionManager)
  4. 修改与版本对比 (diff)
  5. 导出 PPTX (PPTExporter)
  6. 导出 DOCX (DOCExporter)
  7. 导出字节流

用法：
  python scripts/integration_test.py        # 默认模式（不依赖 API Key）
  python scripts/integration_test.py -v      # 详细输出

输出目录：
  output/integration_test/
    ├── 01-outline.json
    ├── 02-scripts.json
    ├── 03-merged_nodes.json
    ├── 04-versions.json
    ├── 04-diff_v1_v2.json
    ├── 05-output.pptx
    ├── 06-output.docx
    └── 07-export_bytes.pptx

退出码：
  0 = 全部通过, 1 = 任意阶段失败
"""

import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

# ---------------------------------------------------------------------------
# 确保能从项目根目录导入
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # 项目根目录
sys.path.insert(0, str(PROJECT_ROOT))


def _check_imports():
    """检查必需模块可供导入"""
    required = [
        "ai_engine.gen.outline",
        "ai_engine.gen.node",
        "ai_engine.gen.version",
        "ai_engine.gen.export_ppt",
        "ai_engine.gen.export_doc",
        "ai_engine.gen.preview",
    ]
    for mod in required:
        __import__(mod)
        print(f"  ✓  {mod}")


# ---------------------------------------------------------------------------
# 输出目录
# ---------------------------------------------------------------------------

OUTPUT = PROJECT_ROOT / "output" / "integration_test"
VERBOSE = "-v" in sys.argv or "--verbose" in sys.argv


def log(msg: str):
    print(msg)


def log_v(msg: str):
    if VERBOSE:
        print(msg)


def dump_json(filename: str, data):
    """写入 JSON 到输出目录"""
    path = OUTPUT / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log_v(f"    → {path.relative_to(PROJECT_ROOT)}")
    return path


# ============================================================================
# Stage 1: 大纲构建
# ============================================================================

def stage1_outline():
    """
    Markdown → 大纲 (OutlineBuilder)
    验证：输出包含 nodes 数组，每个节点有 node_id/title/summary
    """
    print("\n" + "=" * 60)
    print("Stage 1: 大纲构建 OutlineBuilder")
    print("=" * 60)

    from ai_engine.gen.outline import OutlineBuilder

    markdown = """# 排序算法入门

## 1.1 什么是排序
排序是计算机科学中最基本的操作之一。
将一组无序数据按特定顺序重新排列。

## 1.2 冒泡排序
重复遍历列表，比较相邻元素并交换顺序错误的元素。
时间复杂度 O(n²)，适合小规模数据。

## 1.3 快速排序
分治策略：选基准值(pivot)，分区后递归排序。
平均 O(n log n)，实际应用最广泛。

## 1.4 归并排序
分治策略：递归分割至单元素，再两两合并。
稳定 O(n log n)，但需要额外 O(n) 空间。

## 1.5 性能对比
冒泡: O(n²) | 选择: O(n²) | 插入: O(n²)
快排: O(n log n) | 归并: O(n log n)
堆排: O(n log n)
"""

    builder = OutlineBuilder()

    # 方法 1: build_from_markdown
    result = builder.build_from_markdown(markdown, "排序算法入门")
    nodes = result.get("nodes", [])

    assert len(nodes) > 0, "nodes 数组不能为空"
    required = {"node_id", "title", "summary", "source_span", "prerequisites"}
    for node in nodes:
        missing = required - set(node.keys())
        assert not missing, f"节点 {node.get('node_id')} 缺少字段: {missing}"

    dump_json("01-outline.json", result)
    log(f"  ✓  生成 {len(nodes)} 个大纲节点")
    for n in nodes[:3]:
        log_v(f"      {n['node_id']}: {n['title']}")
    if len(nodes) > 3:
        log(f"      ... 共 {len(nodes)} 个节点 (显示前3)")
    return nodes


# ============================================================================
# Stage 2: 节点讲稿生成
# ============================================================================

def stage2_scripts(nodes):
    """
    大纲节点 → 讲稿内容 (NodeGenerator)
    验证：每个节点绑定 script, scripts 数与 nodes 数一致
    """
    print("\n" + "=" * 60)
    print("Stage 2: 节点讲稿 NodeGenerator")
    print("=" * 60)

    from ai_engine.gen.node import NodeGenerator

    generator = NodeGenerator()
    result = generator.generate_all(nodes, "# 排序算法入门\n\n排序算法是最基本的算法之一。", "排序算法入门")
    scripts = result.get("scripts", [])

    assert len(scripts) == len(nodes), \
        f"scripts 数 ({len(scripts)}) 应与 nodes 数 ({len(nodes)}) 一致"

    for s in scripts:
        assert "node_id" in s, f"script 缺少 node_id: {s}"
        assert "script" in s or "segments" in s, \
            f"script {s.get('node_id')} 缺少 script 或 segments"

    dump_json("02-scripts.json", result)
    log(f"  ✓  生成 {len(scripts)} 个节点讲稿")
    for s in scripts[:3]:
        script_preview = (s.get("script") or "")[:50]
        log_v(f"      {s['node_id']}: {script_preview}...")

    # 合并节点数据供后续使用
    merged = []
    for node in nodes:
        script_data = next(
            (s for s in scripts if s.get("node_id") == node.get("node_id")),
            {"script": "", "segments": []},
        )
        merged.append({**node,
                       "script": script_data.get("script", ""),
                       "segments": script_data.get("segments", [])})

    dump_json("03-merged_nodes.json", merged)
    log(f"  ✓  合并 {len(merged)} 个完整节点")
    return merged


# ============================================================================
# Stage 3: 版本管理
# ============================================================================

def stage3_version(gen_id, merged_nodes):
    """
    版本保存 + 修改 + 版本对比 (VersionManager)
    验证：save → list → diff → revert → lock 全链路
    """
    print("\n" + "=" * 60)
    print("Stage 3: 版本管理 VersionManager")
    print("=" * 60)

    from ai_engine.gen.version import get_version_manager

    vm = get_version_manager()

    # 3a: 保存 v1
    v1 = vm.save_snapshot(gen_id, merged_nodes, "初稿")
    assert v1.version_number == 1
    log(f"  ✓  保存 v{v1.version_number}: {v1.summary}")

    # 3b: 修改几个节点后保存 v2
    modified = merged_nodes.copy()
    if len(modified) >= 2:
        modified[0]["title"] = modified[0]["title"] + "（已修改）"
        modified[0]["content"] = "这是修改后的内容"
    modified.append({
        "node_id": "added_node",
        "title": "新增节点",
        "summary": "这是新增的节点",
        "content": "新节点内容",
        "type": "content",
    })

    v2 = vm.save_snapshot(gen_id, modified, "修改版：调整标题+新增节点")
    assert v2.version_number == 2
    log(f"  ✓  保存 v{v2.version_number}: {v2.summary}")

    # 3c: 列出版本
    versions = vm.list_versions(gen_id)
    assert len(versions) >= 2
    dump_json("04-versions.json", [
        {"version_number": v.version_number, "summary": v.summary,
         "locked": v.locked, "created_at": str(v.created_at)}
        for v in versions
    ])
    log(f"  ✓  版本列表: {len(versions)} 个版本")

    # 3d: diff
    diff = vm.diff(gen_id, 1, 2)
    assert "added" in diff and "removed" in diff and "changed" in diff
    dump_json("04-diff_v1_v2.json", diff)
    log(f"  ✓  diff v1→v2: "
        f"新增 {len(diff['added'])} / "
        f"删除 {len(diff['removed'])} / "
        f"修改 {len(diff['changed'])} / "
        f"相同 {len(diff['same'])}")

    # 3e: 回滚
    reverted = vm.revert_to(gen_id, 1)
    assert reverted.version_number == 3
    assert reverted.parent_version == 1
    log(f"  ✓  回滚 v{reverted.version_number}（基于 v1）: {reverted.summary}")

    # 3f: 锁定 v1
    locked = vm.lock_version(gen_id, 1)
    assert locked.locked
    log(f"  ✓  锁定 v1: locked={locked.locked}")

    return vm


# ============================================================================
# Stage 4: 导出 PPTX
# ============================================================================

def stage4_export_pptx(merged_nodes):
    """
    导出 PPTX (PPTExporter)
    验证：有效 ZIP，包含 [Content_Types].xml，页数 > 0
    """
    print("\n" + "=" * 60)
    print("Stage 4: 导出 PPTX PPTExporter")
    print("=" * 60)

    from ai_engine.gen.export_ppt import PPTExporter, ExportPPTConfig

    output_path = OUTPUT / "05-output.pptx"

    ppt = PPTExporter(ExportPPTConfig(output_dir=str(OUTPUT)))
    result = ppt.export(merged_nodes, "排序算法入门")

    assert result["pages"] > 0
    file_path = Path(result["path"])
    assert file_path.exists()
    assert file_path.stat().st_size > 0

    # 验证 ZIP 结构
    with zipfile.ZipFile(str(file_path)) as z:
        assert "[Content_Types].xml" in z.namelist()
        slides = [n for n in z.namelist() if n.startswith("ppt/slides/slide")]
        assert len(slides) > 0

    log(f"  ✓  PPTX: {result['pages']} 页, "
        f"{result['file_size']} bytes")
    log_v(f"      → {file_path}")

    # 导出字节流
    buf = ppt.export_to_bytes(merged_nodes, "排序算法入门")
    bytes_path = OUTPUT / "07-export_bytes.pptx"
    bytes_path.write_bytes(buf.getvalue())
    assert bytes_path.stat().st_size > 0
    log(f"  ✓  PPTX 字节流: {bytes_path.stat().st_size} bytes")


# ============================================================================
# Stage 5: 导出 DOCX
# ============================================================================

def stage5_export_docx(merged_nodes):
    """
    导出 DOCX (DOCExporter)
    验证：有效 ZIP，包含 word/document.xml
    """
    print("\n" + "=" * 60)
    print("Stage 5: 导出 DOCX DOCExporter")
    print("=" * 60)

    from ai_engine.gen.export_doc import DOCExporter, ExportDocConfig

    doc = DOCExporter(ExportDocConfig(output_dir=str(OUTPUT)))
    result = doc.export(merged_nodes, "排序算法入门")

    assert result["sections"] > 0
    file_path = Path(result["path"])
    assert file_path.exists()
    assert file_path.stat().st_size > 0

    # 验证 ZIP 结构
    buf = doc.export_to_bytes(merged_nodes, "排序算法入门")
    with zipfile.ZipFile(buf) as z:
        assert "word/document.xml" in z.namelist()
        assert "word/document.xml" in z.namelist()  # 不用重复

    # 重命名到输出目录
    doc_path = OUTPUT / "06-output.docx"
    if file_path != doc_path:
        shutil.copy2(str(file_path), str(doc_path))

    log(f"  ✓  DOCX: {result['sections']} sections, "
        f"{result['file_size']} bytes")
    log_v(f"      → {doc_path}")

    # 字节流也被验证了在上面的 ZIP 检查里
    log(f"  ✓  DOCX 字节流: 有效 ZIP")


# ============================================================================
# Stage 6: 预览渲染
# ============================================================================

def stage6_preview(merged_nodes):
    """
    预览渲染 (PreviewRenderer)
    验证：输出 HTML
    """
    print("\n" + "=" * 60)
    print("Stage 6: 预览渲染 PreviewRenderer")
    print("=" * 60)

    from ai_engine.gen.preview import PreviewRenderer

    renderer = PreviewRenderer()
    html = renderer.render(merged_nodes, "排序算法入门")

    assert "<!DOCTYPE html>" in html
    assert "class=\"slide" in html or "slide" in html.lower()

    html_path = OUTPUT / "08-preview.html"
    html_path.write_text(html, encoding="utf-8")
    log(f"  ✓  HTML 预览: {len(html)} chars")
    log_v(f"      → {html_path}")


# ============================================================================
# Stage 7: 互动内容生成
# ============================================================================

def stage7_interactive(merged_nodes):
    """
    互动内容 (InteractiveBuilder)
    """
    print("\n" + "=" * 60)
    print("Stage 7: 互动内容 InteractiveBuilder")
    print("=" * 60)

    from ai_engine.gen.interactive import InteractiveBuilder

    builder = InteractiveBuilder()
    total_items = 0
    for node in merged_nodes[:3]:
        items = builder.build_all(node)
        total_items += len(items)
        log_v(f"    {node.get('node_id')}: {len(items)} 个互动素材")

    assert total_items > 0, "应至少生成一些互动素材"
    log(f"  ✓  共生成 {total_items} 个互动素材（前3个节点）")


# ============================================================================
# 主流程
# ============================================================================

def main():
    print("=" * 60)
    print("  AI Engine 全链路集成测试")
    print("  排序算法入门 — 演示课件")
    print("=" * 60)

    # 清理输出目录
    if OUTPUT.exists():
        shutil.rmtree(str(OUTPUT))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    log(f"输出目录: {OUTPUT.relative_to(PROJECT_ROOT)}/\n")

    # 检查导入
    print("--- 导入检查 ---")
    _check_imports()

    # 执行各个阶段
    try:
        nodes = stage1_outline()
        merged = stage2_scripts(nodes)
        gen_id = "integration_test_course"
        vm = stage3_version(gen_id, merged)
        stage4_export_pptx(merged)
        stage5_export_docx(merged)
        stage6_preview(merged)
        stage7_interactive(merged)

        # 最终统计
        print("\n" + "=" * 60)
        print("  ALL STAGES PASSED ✓")
        print("=" * 60)

        # 输出文件清单
        print("\n输出文件:")
        for f in sorted(OUTPUT.iterdir()):
            size = f.stat().st_size
            label = "bytes"
            if size > 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size} bytes"
            print(f"    {f.name:30s} {size_str:>10s}")

        print("\n退出码: 0")
        return 0

    except AssertionError as e:
        print(f"\n  ✗  FAILED: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n  ✗  ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
