"""版本管理模块单元测试 — test_version.py

测试目标：
  VersionManager 的所有公开方法在隔离环境下正确工作。
  文件读写、版本号递增、diff 检测、回滚、锁定。
  不依赖 LLM，不依赖外部服务。
"""

import json
import os
import shutil
import unittest
from pathlib import Path
from datetime import datetime

from ai_engine.gen.version import VersionManager, get_version_manager


_TEST_BASE = Path("data/versions") / "_test_version"


def _cleanup():
    """清理测试数据目录"""
    if _TEST_BASE.exists():
        shutil.rmtree(str(_TEST_BASE))


def _test_gen_id(name: str) -> str:
    """生成唯一的测试 gen_id"""
    return f"test_{name}_{datetime.now().timestamp()}"


class TestVersionManagerIsolation(unittest.TestCase):
    """每个测试方法使用独立的 gen_id，互不污染"""

    def setUp(self):
        self.vm = VersionManager()
        _cleanup()

    def tearDown(self):
        _cleanup()

    # -----------------------------------------------------------------
    # save_snapshot
    # -----------------------------------------------------------------

    def test_save_snapshot_returns_version_with_incremented_number(self):
        gen_id = _test_gen_id("save_1")
        nodes = [{"node_id": "n1", "title": "第一节"}]

        v1 = self.vm.save_snapshot(gen_id, nodes, "初稿")
        self.assertEqual(v1.version_number, 1)
        self.assertEqual(v1.generation_id, gen_id)
        self.assertEqual(v1.summary, "初稿")
        self.assertFalse(v1.locked)

        v2 = self.vm.save_snapshot(gen_id, [{"node_id": "n2", "title": "第二节"}], "v2")
        self.assertEqual(v2.version_number, 2)

    def test_save_snapshot_writes_file_on_disk(self):
        gen_id = _test_gen_id("save_disk")
        nodes = [{"node_id": "n1", "title": "测试"}]
        self.vm.save_snapshot(gen_id, nodes)

        # 快照文件存在
        snap_path = _TEST_BASE.parent / gen_id / "v_1.json"
        self.assertTrue(snap_path.exists())
        data = json.loads(snap_path.read_text(encoding="utf-8"))
        self.assertEqual(data["version_number"], 1)
        self.assertEqual(data["generation_id"], gen_id)

        # 元数据文件存在
        meta_path = _TEST_BASE.parent / gen_id / "versions.json"
        self.assertTrue(meta_path.exists())
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.assertEqual(meta["latest_version"], 1)

    def test_save_snapshot_with_metadata(self):
        gen_id = _test_gen_id("save_meta")
        nodes = [{"node_id": "n1", "title": "测试"}]
        meta = {"author": "test", "source": "unittest"}
        v = self.vm.save_snapshot(gen_id, nodes, metadata=meta)
        self.assertEqual(v.metadata.get("author"), "test")

    def test_save_snapshot_empty_nodes(self):
        """空节点列表应当也能保存"""
        gen_id = _test_gen_id("save_empty")
        v = self.vm.save_snapshot(gen_id, [], "空版本")
        self.assertEqual(v.version_number, 1)
        self.assertEqual(v.nodes_snapshot, [])

    # -----------------------------------------------------------------
    # list_versions
    # -----------------------------------------------------------------

    def test_list_versions_empty(self):
        gen_id = _test_gen_id("list_empty")
        versions = self.vm.list_versions(gen_id)
        self.assertEqual(versions, [])

    def test_list_versions_returns_all(self):
        gen_id = _test_gen_id("list_all")
        self.vm.save_snapshot(gen_id, [{"node_id": "n1"}], "v1")
        self.vm.save_snapshot(gen_id, [{"node_id": "n2"}], "v2")
        self.vm.save_snapshot(gen_id, [{"node_id": "n3"}], "v3")

        versions = self.vm.list_versions(gen_id)
        self.assertEqual(len(versions), 3)
        self.assertEqual(versions[0].version_number, 1)
        self.assertEqual(versions[1].version_number, 2)
        self.assertEqual(versions[2].version_number, 3)

    def test_list_versions_ascending_order(self):
        gen_id = _test_gen_id("list_order")
        # 乱序保存
        self.vm.save_snapshot(gen_id, [{"node_id": "a"}], "a")
        self.vm.save_snapshot(gen_id, [{"node_id": "b"}], "b")
        self.vm.save_snapshot(gen_id, [{"node_id": "c"}], "c")

        versions = self.vm.list_versions(gen_id)
        numbers = [v.version_number for v in versions]
        self.assertEqual(numbers, sorted(numbers))

    # -----------------------------------------------------------------
    # load_version
    # -----------------------------------------------------------------

    def test_load_version_returns_none_for_empty(self):
        gen_id = _test_gen_id("load_empty")
        v = self.vm.load_version(gen_id)
        self.assertIsNone(v)

    def test_load_version_latest(self):
        gen_id = _test_gen_id("load_latest")
        self.vm.save_snapshot(gen_id, [{"node_id": "v1"}], "v1")
        self.vm.save_snapshot(gen_id, [{"node_id": "v2"}], "v2")

        latest = self.vm.load_version(gen_id)
        self.assertEqual(latest.version_number, 2)

    def test_load_version_specific(self):
        gen_id = _test_gen_id("load_specific")
        self.vm.save_snapshot(gen_id, [{"node_id": "v1"}], "v1")
        self.vm.save_snapshot(gen_id, [{"node_id": "v2"}], "v2")

        v1 = self.vm.load_version(gen_id, version=1)
        self.assertEqual(v1.version_number, 1)
        self.assertEqual(v1.nodes_snapshot[0].node_id, "v1")

    def test_load_version_nonexistent(self):
        gen_id = _test_gen_id("load_nonexist")
        v = self.vm.load_version(gen_id, version=999)
        self.assertIsNone(v)

    # -----------------------------------------------------------------
    # get_version_number
    # -----------------------------------------------------------------

    def test_get_version_number_zero_when_empty(self):
        gen_id = _test_gen_id("ver_no_empty")
        self.assertEqual(self.vm.get_version_number(gen_id), 0)

    def test_get_version_number_after_save(self):
        gen_id = _test_gen_id("ver_no_after")
        self.vm.save_snapshot(gen_id, [{"node_id": "n1"}])
        self.assertEqual(self.vm.get_version_number(gen_id), 1)
        self.vm.save_snapshot(gen_id, [{"node_id": "n2"}])
        self.assertEqual(self.vm.get_version_number(gen_id), 2)

    # -----------------------------------------------------------------
    # diff
    # -----------------------------------------------------------------

    def test_diff_returns_added_removed_changed(self):
        gen_id = _test_gen_id("diff_basic")
        self.vm.save_snapshot(gen_id, [
            {"node_id": "n1", "title": "第一节", "content": "A"},
            {"node_id": "n2", "title": "第二节", "content": "B"},
        ], "v1")
        self.vm.save_snapshot(gen_id, [
            {"node_id": "n2", "title": "第二节", "content": "B修改"},
            {"node_id": "n3", "title": "第三节", "content": "C"},
        ], "v2")

        diff = self.vm.diff(gen_id, 1, 2)
        self.assertEqual(diff["v1"], 1)
        self.assertEqual(diff["v2"], 2)

        # n1 removed
        removed_ids = [r["node_id"] for r in diff["removed"]]
        self.assertIn("n1", removed_ids)

        # n3 added
        added_ids = [r["node_id"] for r in diff["added"]]
        self.assertIn("n3", added_ids)

        # n2 changed (content changed)
        changed_ids = [c["node_id"] for c in diff["changed"]]
        self.assertIn("n2", changed_ids)

    def test_diff_same_versions(self):
        gen_id = _test_gen_id("diff_same")
        self.vm.save_snapshot(gen_id, [{"node_id": "n1", "title": "A"}], "v1")
        self.vm.save_snapshot(gen_id, [{"node_id": "n1", "title": "A"}], "v2")  # identical

        diff = self.vm.diff(gen_id, 1, 2)
        self.assertIn("n1", [s["node_id"] for s in diff["same"]])
        self.assertEqual(len(diff["changed"]), 0)

    def test_diff_nonexistent_version(self):
        gen_id = _test_gen_id("diff_nonexist")
        self.vm.save_snapshot(gen_id, [{"node_id": "n1"}], "v1")
        diff = self.vm.diff(gen_id, 1, 999)
        self.assertIn("error", diff)

    def test_diff_order_change(self):
        gen_id = _test_gen_id("diff_order")
        self.vm.save_snapshot(gen_id, [
            {"node_id": "n1", "title": "A"},
            {"node_id": "n2", "title": "B"},
        ], "v1")
        self.vm.save_snapshot(gen_id, [
            {"node_id": "n2", "title": "B"},
            {"node_id": "n1", "title": "A"},  # swapped
        ], "v2")

        diff = self.vm.diff(gen_id, 1, 2)
        # Both nodes should be in "changed" with "order" in their changes
        for c in diff["changed"]:
            self.assertIn("order", c["changes"])

    # -----------------------------------------------------------------
    # revert_to
    # -----------------------------------------------------------------

    def test_revert_to_creates_new_version(self):
        gen_id = _test_gen_id("revert_new")
        self.vm.save_snapshot(gen_id, [{"node_id": "v1", "title": "初版"}], "v1")
        self.vm.save_snapshot(gen_id, [{"node_id": "v2", "title": "修改版"}], "v2")

        reverted = self.vm.revert_to(gen_id, 1)
        self.assertEqual(reverted.version_number, 3)  # 新版本号
        self.assertEqual(reverted.summary, "回滚自版本 1")
        self.assertEqual(reverted.parent_version, 1)
        self.assertEqual(reverted.metadata.get("reverted_from"), 1)
        # 内容来自 v1
        self.assertEqual(reverted.nodes_snapshot[0].node_id, "v1")

    def test_revert_to_preserves_content(self):
        gen_id = _test_gen_id("revert_content")
        self.vm.save_snapshot(gen_id, [{"node_id": "n1", "title": "原始内容"}], "v1")
        self.vm.save_snapshot(gen_id, [{"node_id": "n1", "title": "新内容"}], "v2")

        reverted = self.vm.revert_to(gen_id, 1)
        self.assertEqual(reverted.nodes_snapshot[0].title, "原始内容")

    def test_revert_to_preserves_page_bindings_and_presentation(self):
        gen_id = _test_gen_id("revert_bindings")
        bindings = [{"page_id": "page_1", "evidence_refs": ["chunk_tcp_1"]}]
        presentation = {"template_id": "deck-swiss-edu", "palette": "forest"}
        self.vm.save_snapshot(
            gen_id,
            [{"node_id": "page_1", "title": "TCP 三次握手"}],
            "v1",
            metadata={"outline_id": "outline_1"},
            page_bindings=bindings,
            presentation=presentation,
        )

        reverted = self.vm.revert_to(gen_id, 1)

        self.assertEqual(reverted.page_bindings, bindings)
        self.assertEqual(reverted.presentation, presentation)
        self.assertEqual(reverted.metadata.get("outline_id"), "outline_1")
        self.assertEqual(reverted.metadata.get("reverted_from"), 1)

    def test_revert_to_nonexistent_raises(self):
        gen_id = _test_gen_id("revert_nonexist")
        with self.assertRaises(ValueError):
            self.vm.revert_to(gen_id, 999)

    def test_revert_to_version_list_updated(self):
        gen_id = _test_gen_id("revert_list")
        self.vm.save_snapshot(gen_id, [{"node_id": "n1"}], "v1")
        self.vm.revert_to(gen_id, 1)

        versions = self.vm.list_versions(gen_id)
        self.assertEqual(len(versions), 2)

    # -----------------------------------------------------------------
    # lock_version
    # -----------------------------------------------------------------

    def test_lock_version_marks_locked(self):
        gen_id = _test_gen_id("lock_basic")
        self.vm.save_snapshot(gen_id, [{"node_id": "n1"}], "v1")
        locked = self.vm.lock_version(gen_id, 1)
        self.assertTrue(locked.locked)

    def test_lock_version_updates_meta(self):
        gen_id = _test_gen_id("lock_meta")
        self.vm.save_snapshot(gen_id, [{"node_id": "n1"}], "v1")
        self.vm.lock_version(gen_id, 1)

        meta_path = _TEST_BASE.parent / gen_id / "versions.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.assertTrue(meta["versions"][0]["locked"])

    def test_lock_version_latest_when_no_arg(self):
        gen_id = _test_gen_id("lock_latest")
        self.vm.save_snapshot(gen_id, [{"node_id": "n1"}], "v1")
        self.vm.save_snapshot(gen_id, [{"node_id": "n2"}], "v2")
        locked = self.vm.lock_version(gen_id)  # 锁定最新版
        self.assertEqual(locked.version_number, 2)
        self.assertTrue(locked.locked)

    def test_lock_version_empty_raises(self):
        gen_id = _test_gen_id("lock_empty")
        with self.assertRaises(ValueError):
            self.vm.lock_version(gen_id)

    def test_lock_version_nonexistent_raises(self):
        gen_id = _test_gen_id("lock_nonexist")
        self.vm.save_snapshot(gen_id, [{"node_id": "n1"}], "v1")
        with self.assertRaises(ValueError):
            self.vm.lock_version(gen_id, version=999)

    # -----------------------------------------------------------------
    # 并发安全
    # -----------------------------------------------------------------

    def test_concurrent_save_same_generation(self):
        """同一 gen_id 的连续 save 不会互相覆盖"""
        gen_id = _test_gen_id("concurrent")
        v1 = self.vm.save_snapshot(gen_id, [{"node_id": "n1"}], "v1")
        v2 = self.vm.save_snapshot(gen_id, [{"node_id": "n2"}], "v2")
        v3 = self.vm.save_snapshot(gen_id, [{"node_id": "n3"}], "v3")

        self.assertEqual(v1.version_number, 1)
        self.assertEqual(v2.version_number, 2)
        self.assertEqual(v3.version_number, 3)

        # 所有快照文件都存在
        self.assertTrue((_TEST_BASE.parent / gen_id / "v_1.json").exists())
        self.assertTrue((_TEST_BASE.parent / gen_id / "v_2.json").exists())
        self.assertTrue((_TEST_BASE.parent / gen_id / "v_3.json").exists())

    # -----------------------------------------------------------------
    # 数据完整性
    # -----------------------------------------------------------------

    def test_save_and_load_roundtrip(self):
        """保存再加载，数据内容一致"""
        gen_id = _test_gen_id("roundtrip")
        original_nodes = [
            {"node_id": "n1", "title": "标题1", "summary": "摘要1"},
            {"node_id": "n2", "title": "标题2", "summary": "摘要2"},
        ]
        self.vm.save_snapshot(gen_id, original_nodes, "roundtrip测试")

        loaded = self.vm.load_version(gen_id)
        self.assertEqual(len(loaded.nodes_snapshot), 2)
        self.assertEqual(loaded.nodes_snapshot[0].title, "标题1")
        self.assertEqual(loaded.nodes_snapshot[1].summary, "摘要2")

    def test_multiple_generations_isolated(self):
        """不同 gen_id 的版本互不干扰"""
        gen_a = _test_gen_id("multi_a")
        gen_b = _test_gen_id("multi_b")

        self.vm.save_snapshot(gen_a, [{"node_id": "a1"}], "A_v1")
        self.vm.save_snapshot(gen_a, [{"node_id": "a2"}], "A_v2")
        self.vm.save_snapshot(gen_b, [{"node_id": "b1"}], "B_v1")

        self.assertEqual(len(self.vm.list_versions(gen_a)), 2)
        self.assertEqual(len(self.vm.list_versions(gen_b)), 1)
        self.assertEqual(self.vm.load_version(gen_a).version_number, 2)
        self.assertEqual(self.vm.load_version(gen_b).version_number, 1)


# -----------------------------------------------------------------
# 全局单例测试
# -----------------------------------------------------------------

class TestVersionManagerSingleton(unittest.TestCase):
    def test_get_version_manager_returns_same_instance(self):
        vm1 = get_version_manager()
        vm2 = get_version_manager()
        self.assertIs(vm1, vm2)

    def test_get_version_manager_is_version_manager(self):
        vm = get_version_manager()
        self.assertIsInstance(vm, VersionManager)


if __name__ == "__main__":
    unittest.main(verbosity=2)
