# -*- coding: utf-8 -*-
"""导出产物 MinIO 上传链路离线验证脚本 (verify_export_upload.py)

不依赖真实 MinIO 服务，全部用 mock / 降级行为断言：
  T1  MINIO_ENDPOINT 未配置  → skipped + 原因（无默认值语义）
  T1b minio 包未安装         → skipped + 友好原因，本地文件保留
  T2  mock 上传成功          → uploaded + minio:// URL，fput_object 被调用
  T3  mock bucket 不存在     → 自动 make_bucket 后上传成功
  T4  mock 上传抛异常        → failed + 原因，异常不外泄
  T5  本地文件不存在         → failed
  T6  _run_export 降级契约   → 上传失败时任务仍为 done、本地路径保留、upload_status=failed
  T7  _run_export 上传成功   → minio_path 为 minio:// URL、upload_status=uploaded
  T8  BOTH 格式两个文件都上传（回归：旧代码 elif 只上传一个）

运行：python scripts/verify_export_upload.py   （退出码 0 = 全部 PASS）
"""

import asyncio
import io
import os
import sys
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from ai_engine.gen import export_upload
from ai_engine.gen.export_upload import upload_export_file

RESULTS = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    RESULTS.append((name, status, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))


class FakeMinioClient:
    """可编程 MinIO 客户端 mock。"""
    behavior = {"bucket_exists": True, "fail_fput": False}
    calls = []

    def __init__(self, endpoint, access_key=None, secret_key=None, secure=False):
        FakeMinioClient.calls.append(("init", endpoint, secure))

    def bucket_exists(self, bucket):
        FakeMinioClient.calls.append(("bucket_exists", bucket))
        return FakeMinioClient.behavior["bucket_exists"]

    def make_bucket(self, bucket):
        FakeMinioClient.calls.append(("make_bucket", bucket))

    def fput_object(self, bucket, object_name, file_path):
        if FakeMinioClient.behavior["fail_fput"]:
            raise ConnectionError("connection refused (mock)")
        FakeMinioClient.calls.append(("fput_object", bucket, object_name, file_path))


def install_fake_minio():
    module = types.ModuleType("minio")
    module.Minio = FakeMinioClient
    sys.modules["minio"] = module


def remove_fake_minio():
    sys.modules.pop("minio", None)


def make_temp_file(name: str) -> str:
    p = Path(PROJECT_ROOT) / "data" / "verify_tmp"
    p.mkdir(parents=True, exist_ok=True)
    f = p / name
    f.write_bytes(b"fake-export-bytes")
    return str(f)


def make_sample_nodes():
    return [{"title": "排序算法", "node_type": "content", "content": "冒泡排序与快排对比。"}]


# ---------------------------------------------------------------------------
def main():
    sample = make_temp_file("sample.pptx")

    # 测试内显式控制 MINIO_ENDPOINT（新语义：未配置 → skipped，不再有默认值）
    old_endpoint = os.environ.pop("MINIO_ENDPOINT", None)

    # ---- T1: MINIO_ENDPOINT 未配置 → skipped；minio 包未安装 → skipped ----
    remove_fake_minio()
    r = upload_export_file(sample, "exports/t1.pptx")
    check("T1 MINIO_ENDPOINT未配置 → skipped", r.upload_status == "skipped", r.reason)
    check("T1 原因说明未配置", "MINIO_ENDPOINT" in r.reason, r.reason)
    check("T1 本地路径保留", r.local_path == sample)

    os.environ["MINIO_ENDPOINT"] = "localhost:9000"
    r = upload_export_file(sample, "exports/t1b.pptx")
    check("T1b minio未安装 → skipped", r.upload_status == "skipped", r.reason)
    check("T1b 本地路径保留", r.local_path == sample)

    # ---- T2: mock 上传成功 ----
    install_fake_minio()
    FakeMinioClient.behavior = {"bucket_exists": True, "fail_fput": False}
    FakeMinioClient.calls = []
    r = upload_export_file(sample, "exports/t2.pptx")
    check("T2 上传成功 → uploaded", r.upload_status == "uploaded", str(r.minio_path))
    check("T2 minio URL 格式", r.minio_path == "minio://teaching/exports/t2.pptx", r.minio_path or "")
    check("T2 fput_object 被调用", any(c[0] == "fput_object" for c in FakeMinioClient.calls))

    # ---- T3: bucket 不存在自动创建 ----
    FakeMinioClient.behavior = {"bucket_exists": False, "fail_fput": False}
    FakeMinioClient.calls = []
    r = upload_export_file(sample, "exports/t3.pptx", bucket="teaching")
    check("T3 bucket 预检自动创建", r.upload_status == "uploaded"
          and ("make_bucket", "teaching") in FakeMinioClient.calls, r.reason)

    # ---- T4: 上传异常 → failed 不外泄 ----
    FakeMinioClient.behavior = {"bucket_exists": True, "fail_fput": True}
    r = upload_export_file(sample, "exports/t4.pptx")
    check("T4 上传异常 → failed", r.upload_status == "failed", r.reason)
    check("T4 原因含 endpoint", "endpoint=" in r.reason)
    check("T4 本地路径保留", r.local_path == sample)
    remove_fake_minio()

    # ---- T5: 本地文件不存在 ----
    r = upload_export_file("Z:/not/exist/file.pptx", "exports/t5.pptx")
    check("T5 文件不存在 → failed", r.upload_status == "failed")

    # ---- T6/T7/T8: _run_export 降级契约（导入真实 main.py） ----
    from ai_engine import main as app_main
    from ai_engine.core.schema import ExportFormat, ExportJob, ExportStatus

    async def run_export_case(job_id, fmt, nodes):
        job = ExportJob(job_id=job_id, generation_id="gen_x", format=fmt,
                        status=ExportStatus.PENDING)
        app_main._export_tasks[job_id] = job
        await app_main._run_export(job_id, nodes, fmt)
        return app_main._export_tasks[job_id]

    nodes = make_sample_nodes()

    # T6: 上传失败 → done + 本地路径 + upload_status=failed
    install_fake_minio()
    FakeMinioClient.behavior = {"bucket_exists": True, "fail_fput": True}
    job = asyncio.run(run_export_case("exp_t6", ExportFormat.PPTX, nodes))
    check("T6 上传失败任务仍为 done", job.status == ExportStatus.DONE, str(job.status))
    check("T6 upload_status=failed",
          (job.metadata or {}).get("upload_status") == "failed",
          str((job.metadata or {}).get("upload_error")))
    check("T6 minio_path 保留本地路径",
          bool(job.minio_path) and not job.minio_path.startswith("minio://"), str(job.minio_path))
    check("T6 error 记录原因", bool(job.error))

    # T7: 上传成功 → minio:// + upload_status=uploaded
    FakeMinioClient.behavior = {"bucket_exists": True, "fail_fput": False}
    job = asyncio.run(run_export_case("exp_t7", ExportFormat.PPTX, nodes))
    check("T7 upload_status=uploaded",
          (job.metadata or {}).get("upload_status") == "uploaded")
    check("T7 minio_path 为 minio:// URL",
          bool(job.minio_path) and job.minio_path.startswith("minio://teaching/exports/exp_t7.pptx"),
          str(job.minio_path))

    # T8: BOTH 格式 → pptx 与 docx 都上传
    # 2026-08-31 起 BOTH 模式同步产出 HTML5 互动小游戏（A12 赛题 4c/5c），
    # 上传清单扩展为 pptx/docx/html 三件，断言同步更新（检查数不变）。
    FakeMinioClient.behavior = {"bucket_exists": True, "fail_fput": False}
    FakeMinioClient.calls = []
    job = asyncio.run(run_export_case("exp_t8", ExportFormat.BOTH, nodes))
    uploads = (job.metadata or {}).get("uploads", [])
    exts = sorted(u["local_path"].rsplit(".", 1)[-1] for u in uploads)
    check("T8 BOTH 三个文件都上传(pptx/docx/html)", exts == ["docx", "html", "pptx"], str(exts))
    check("T8 upload_status=uploaded", (job.metadata or {}).get("upload_status") == "uploaded")
    remove_fake_minio()

    # 清理临时目录
    import shutil
    shutil.rmtree(Path(PROJECT_ROOT) / "data" / "verify_tmp", ignore_errors=True)

    # 还原 MINIO_ENDPOINT 环境变量
    if old_endpoint is None:
        os.environ.pop("MINIO_ENDPOINT", None)
    else:
        os.environ["MINIO_ENDPOINT"] = old_endpoint

    failed = [r for r in RESULTS if r[1] == "FAIL"]
    print()
    print(f"===== verify_export_upload: {len(RESULTS) - len(failed)}/{len(RESULTS)} PASS =====")
    if failed:
        for name, _, detail in failed:
            print(f"  FAIL: {name} {detail}")
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
