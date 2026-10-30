# 使用 Python 3.12 的精简版基础镜像。
FROM python:3.12-slim

# 设置三个环境变量；反斜杠连接后续行，保持为同一条 ENV 指令。
# PYTHONDONTWRITEBYTECODE=1：禁止生成 Python 字节码文件。
# PYTHONUNBUFFERED=1：禁用输出缓冲，让容器日志及时显示。
# PIP_NO_CACHE_DIR=1：禁用 pip 下载缓存，减少镜像占用。
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 设置后续指令与应用的工作目录。
WORKDIR /app

# apt-get update：更新系统包索引；反斜杠连接后续步骤。
# apt-get install：安装编译工具、PostgreSQL 开发库和健康检查所需的 curl。
# rm：删除 apt 包索引，减少镜像大小。
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖清单，便于利用镜像构建缓存。
COPY requirements.txt .
# 按 requirements.txt 中的版本安装 Python 依赖。
RUN pip install -r requirements.txt

# 复制构建上下文中的项目文件；当前附件不含应用源码，且未提供 .dockerignore。
COPY . .

# 声明应用监听的容器端口；实际端口映射由 Compose 指定。
EXPOSE 8000

# HEALTHCHECK：每 30 秒检查一次，超时 3 秒，启动宽限期 20 秒。
# CMD curl：请求应用健康接口；请求失败时以非零状态报告不健康。
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

# 默认启动 app.main 模块中的 app 对象，监听全部网卡的 8000 端口。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
