from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import subprocess
import sys

# 初始化FastAPI应用
app = FastAPI(title="文档解析服务")

# 解决前端跨域（必须加，否则前端调接口报错）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 定位ai_engine目录（自动适配你的路径）
AI_ENGINE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_engine")
os.makedirs(AI_ENGINE_DIR, exist_ok=True)

# 健康检查接口（验证服务是否启动）
@app.get("/")
def health_check():
    return {
        "code": 200,
        "msg": "服务正常",
        "data": {"ai_engine_path": AI_ENGINE_DIR}
    }

# 核心：文档解析接口（对接前端）
@app.post("/api/parse-document")
async def parse_document(file: UploadFile = File(...)):
    # 1. 校验文件类型
    suffix = file.filename.lower().split(".")[-1]
    if suffix not in ["pdf", "pptx"]:
        raise HTTPException(400, "仅支持PDF/PPTX文件")
    
    # 2. 保存文件
    save_path = os.path.join(AI_ENGINE_DIR, file.filename)
    try:
        with open(save_path, "wb") as f:
            f.write(await file.read())
        
        # 3. 调用parser.py解析
        cmd = [sys.executable, os.path.join(AI_ENGINE_DIR, "parser.py"), file.filename]
        result = subprocess.run(
            cmd, cwd=AI_ENGINE_DIR, capture_output=True, text=True, encoding="utf-8", errors="ignore"
        )
        
        # 4. 返回结果
        if result.returncode != 0:
            raise HTTPException(500, f"解析失败：{result.stderr.strip() or '无错误信息'}")
        
        return {
            "code": 200,
            "msg": "解析成功",
            "data": {"filename": file.filename, "result": result.stdout.strip()}
        }
    finally:
        # 5. 清理文件
        if os.path.exists(save_path):
            os.remove(save_path)

# 启动服务
if __name__ == "__main__":
    print("=== 文档解析服务启动 ===")
    print(f"接口文档：http://127.0.0.1:8000/docs")
    print(f"健康检查：http://127.0.0.1:8000")
    print("========================")