# syntax=docker/dockerfile:1
# 使用固定 Python 主次版本的精简镜像。
FROM python:3.12-slim
# 禁止生成字节码，并即时输出服务日志。
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
# 二进制 psycopg wheel 无需系统编译工具。
COPY requirements.txt .
# 可选代理 CA 通过 BuildKit secret 临时挂载，不进入镜像；普通部署无需传入。
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install -r requirements.txt
# 不复制工作区数据、密码或 Git 元数据（由 .dockerignore 排除）。
COPY . .
# 以非 root 用户运行；数据卷保存视频与本地数据库。
RUN useradd --create-home training && mkdir -p /app/data && chown -R training:training /app
USER training
EXPOSE 8000
# 实际请求健康接口；不依赖 curl。
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
# 单 worker 与应用内登录限流相匹配；启动时执行数据库迁移。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
