"""兼容旧文档的冒烟入口；实际执行完整 API 集成测试并保留退出状态。"""
import subprocess
import sys
from pathlib import Path

if __name__ == '__main__':
    raise SystemExit(subprocess.call([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], cwd=Path(__file__).resolve().parent.parent))
