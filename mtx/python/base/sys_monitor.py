"""系统资源监控工具"""
import os
import time

def get_memory_info():
    """获取系统内存信息"""
    try:
        with open('/proc/meminfo', 'r') as f:
            lines = f.readlines()
            mem_info = {}
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    mem_info[key.strip()] = value.strip()
            
            total = int(mem_info.get('MemTotal', '0').split()[0]) // 1024  # MB
            available = int(mem_info.get('MemAvailable', '0').split()[0]) // 1024  # MB
            swap_total = int(mem_info.get('SwapTotal', '0').split()[0]) // 1024  # MB
            swap_free = int(mem_info.get('SwapFree', '0').split()[0]) // 1024  # MB
            
            return {
                'total_mb': total,
                'available_mb': available,
                'used_mb': total - available,
                'swap_total_mb': swap_total,
                'swap_used_mb': swap_total - swap_free
            }
    except Exception as e:
        return {'error': str(e)}

def print_memory_warning():
    """打印内存警告信息"""
    info = get_memory_info()
    if 'error' in info:
        print(f"[SYS] Failed to get memory info: {info['error']}", flush=True)
        return
    
    print(f"[SYS] Memory: {info['used_mb']}/{info['total_mb']}MB used, "
          f"{info['available_mb']}MB available, "
          f"Swap: {info['swap_used_mb']}/{info['swap_total_mb']}MB used", flush=True)
    
    # 警告：内存不足
    if info['available_mb'] < 1000:  # 小于1GB可用
        print(f"[SYS] ⚠️⚠️⚠️ LOW MEMORY! Only {info['available_mb']}MB available!", flush=True)
    
    # 警告：使用了swap
    if info['swap_used_mb'] > 100:
        print(f"[SYS] ⚠️⚠️⚠️ SWAPPING! {info['swap_used_mb']}MB swap in use - this causes stuttering!", flush=True)

def get_shm_files():
    """列出当前打开的共享内存文件"""
    try:
        shm_dir = '/dev/shm'
        if not os.path.exists(shm_dir):
            return []
        
        files = []
        for name in os.listdir(shm_dir):
            path = os.path.join(shm_dir, name)
            if os.path.isfile(path):
                size = os.path.getsize(path) // (1024 * 1024)  # MB
                files.append((name, size))
        return files
    except Exception as e:
        return [('error', str(e))]

def print_shm_info():
    """打印共享内存信息"""
    files = get_shm_files()
    if not files:
        print("[SYS] No shared memory files found", flush=True)
        return
    
    total_size = sum(size for name, size in files if name != 'error')
    print(f"[SYS] Shared memory: {len(files)} files, {total_size}MB total", flush=True)
    
    if len(files) > 50:
        print(f"[SYS] ⚠️  Too many SHM files: {len(files)} - possible leak!", flush=True)
