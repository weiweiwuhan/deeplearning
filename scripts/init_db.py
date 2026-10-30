"""可选的独立初始化命令：在仓库根目录执行 python -m scripts.init_db。"""
from app.main import bootstrap

if __name__ == '__main__':
    bootstrap()
    print('数据库迁移完成；首次运行时已创建管理员。')
