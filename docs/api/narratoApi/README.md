# narratoApi

NarratoAI 多用户业务层的独立 FastAPI 服务。该服务只负责 Web 业务、持久化与编排，
不导入或执行 Core 视频处理能力。

开发环境使用 Python 3.12：

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/uvicorn narrato_api.main:app
```
