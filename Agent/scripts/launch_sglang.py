"""使用指定进程名启动 SGLang 命令行入口。"""

import os
import runpy
import sys

from setproctitle import setproctitle


if __name__ == "__main__":
    sglang_bin = sys.argv[1]
    sys.argv = [sglang_bin, *sys.argv[2:]]
    setproctitle(os.environ["SGLANG_PROCESS_NAME"])
    runpy.run_path(sglang_bin, run_name="__main__")
