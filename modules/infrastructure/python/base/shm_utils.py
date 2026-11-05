import os
import mmap
import ctypes
import ctypes.util
import time

O_RDONLY = os.O_RDONLY
O_RDWR = os.O_RDWR

PROT_READ = 1
PROT_WRITE = 2
MAP_SHARED = 1

libc = ctypes.CDLL(ctypes.util.find_library('c'))
libc.shm_open.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
libc.shm_open.restype = ctypes.c_int

def open_and_map(name: str):
    """打开并映射共享内存，带详细的性能监控"""
    t_start = time.time()
    
    if not name.startswith('/'):
        name = '/' + name
    
    # 步骤1：shm_open
    t_before_open = time.time()
    fd = libc.shm_open(name.encode('utf-8'), O_RDWR, 0)
    t_after_open = time.time()
    if (t_after_open - t_before_open) > 0.1:
        print(f"[SHM] ⚠️  shm_open took {t_after_open - t_before_open:.3f}s for {name}", flush=True)
    
    if fd < 0:
        raise RuntimeError(f'shm_open failed for {name}')
    
    # 步骤2：fstat
    t_before_fstat = time.time()
    st = os.fstat(fd)
    t_after_fstat = time.time()
    if (t_after_fstat - t_before_fstat) > 0.1:
        print(f"[SHM] ⚠️  fstat took {t_after_fstat - t_before_fstat:.3f}s", flush=True)
    
    if st.st_size <= 0:
        os.close(fd)
        raise RuntimeError(f'fstat failed: size <= 0 for {name}')
    
    # 步骤3：mmap
    t_before_mmap = time.time()
    mm = mmap.mmap(fd, int(st.st_size), access=mmap.ACCESS_WRITE)
    t_after_mmap = time.time()
    if (t_after_mmap - t_before_mmap) > 0.1:
        print(f"[SHM] ⚠️  mmap took {t_after_mmap - t_before_mmap:.3f}s (size={st.st_size})", flush=True)
    
    # 总时间
    t_end = time.time()
    if (t_end - t_start) > 0.5:
        print(f"[SHM] ⚠️  TOTAL open_and_map took {t_end - t_start:.3f}s "
              f"(open={t_after_open-t_before_open:.3f} fstat={t_after_fstat-t_before_fstat:.3f} "
              f"mmap={t_after_mmap-t_before_mmap:.3f})", flush=True)
    
    return fd, mm, int(st.st_size)

def close_map(fd: int, mm: mmap.mmap):
    try:
        mm.flush()
    except Exception:
        pass
    try:
        mm.close()
    except Exception:
        pass
    try:
        os.close(fd)
    except Exception:
        pass
