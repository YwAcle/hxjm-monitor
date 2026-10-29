import os
import json
import time
import traceback
import multiprocessing as mp
mp.set_start_method("spawn", force=True)
import asyncio
class Worker:
    def __init__(self, out_q: mp.Queue, server_cls):
        # ⚠️ 限制队列大小为1，避免积压！只保留最新帧
        self.in_q = mp.Queue(maxsize=1)
        self.out_q = out_q
        self.server_cls = server_cls  # 传递类而不是 bound method
        self.p = mp.Process(target=self.run, args=(self.in_q, self.out_q, server_cls))
        self.p.daemon = False  # 改为 False，支持优雅关闭
        self.p.start()
        self._shutdown = False
    
    def stop(self):
        """优雅关闭 worker"""
        self._shutdown = True
        try:
            # 发送终止信号（None 作为 meta）
            self.in_q.put((b"SHUTDOWN", None), timeout=5.0)
        except:
            pass
    
    def join(self, timeout=None):
        """等待 worker 进程结束"""
        self.p.join(timeout=timeout)
    
    @staticmethod
    def run(in_q: mp.Queue, out_q: mp.Queue, server_cls):
        """Worker 子进程主循环 - 使用 asyncio.run 驱动常驻事件循环"""
        import asyncio
        asyncio.run(Worker._async_main(in_q, out_q, server_cls))
    
    @staticmethod
    async def _async_main(in_q: mp.Queue, out_q: mp.Queue, server_cls):
        """Worker 异步主循环"""
        # 获取当前事件循环
        loop = asyncio.get_running_loop()
        
        # 创建服务器实例（不创建 socket）
        server = server_cls(create_server_socket=False)
        server._loop = loop  # 保存 loop 引用，供 submit 使用
        
        # 仅为需要数据库的算法初始化连接池。
        # SAM3、FastSAM 等纯推理服务没有 db 属性，不应因此退出 worker。
        if hasattr(server, "db") and server.db:
            try:
                await server.db.initialize()
                print(f"[Worker] 数据库连接池初始化完成", flush=True)
            except Exception as e:
                print(f"[Worker] 数据库初始化失败: {e}", flush=True)
                traceback.print_exc()
                # Keep the inference worker alive. ReID can still provide
                # real-time detection/tracking while PostgreSQL is restarting;
                # feature/track persistence will be unavailable for this run.
                server.db = None
        
        # 初始化数据库后，清理未结束的轨迹记录（只有reid任务才有这个方法）
        if hasattr(server, 'cleanup_incomplete_tracklets'):
            try:
                # 在线程池中执行清理方法
                await loop.run_in_executor(None, server.cleanup_incomplete_tracklets)
                print(f"[Worker] 未结束的轨迹记录清理完成", flush=True)
            except Exception as e:
                print(f"[Worker] 清理未结束的轨迹记录失败: {e}", flush=True)
                traceback.print_exc()
        
        # 加载特征库（只有reid任务才加载）
        # 注意：这些方法内部使用了 run_until_complete，但在异步上下文中需要改为 await
        # 为了兼容性，我们在线程池中执行这些同步方法
        if hasattr(server, 'load_target_features') and hasattr(server, 'load_person_features_from_db'):
            try:
                # 这些方法内部使用了 run_until_complete，所以在线程池中执行
                await loop.run_in_executor(None, server.load_target_features)
                await loop.run_in_executor(None, server.load_person_features_from_db)
                print(f"[Worker] 特征库加载完成", flush=True)
            except Exception as e:
                print(f"[Worker] 特征库加载失败: {e}", flush=True)
                traceback.print_exc()
        
        # 初始化模型上下文
        model_ctx = server_cls.init_model_context()
        print(f"[Worker] Model Context Initialized", flush=True)
        
        last_get_time = time.time()
        
        try:
            while True:
                # ========== 时间追踪1：等待队列（异步化） ==========
                t_before_get = time.time()
                try:
                    identity, meta = await loop.run_in_executor(None, in_q.get)
                    id_str = identity[:8].hex() if isinstance(identity, bytes) and len(identity) >= 8 else str(identity)[:16]
                    # print(f"[Worker] ← 收到任务 (identity={id_str}...)", flush=True)
                except Exception as e:
                    print(f"[Worker] 队列获取异常: {e}", flush=True)
                    traceback.print_exc()
                    break
                
                # 检查终止信号
                if meta is None:
                    print(f"[Worker] 收到终止信号，退出", flush=True)
                    break
                
                t_after_get = time.time()
                
                queue_wait_in_worker = t_after_get - t_before_get
                gap_since_last_frame = t_after_get - last_get_time
                last_get_time = t_after_get
                
                # 记录到 meta，供后续使用
                meta["_worker_queue_wait"] = queue_wait_in_worker
                meta["_worker_gap"] = gap_since_last_frame
                meta["_worker_got_at"] = t_after_get
                
                try:
                    # ========== 时间追踪2：处理前 ==========
                    t_before_process = time.time()
                    
                    # ========== 时间追踪3：实际处理（在线程池中执行，不阻塞事件循环） ==========
                    t_before_fn = time.time()
                    if t_before_fn - t_before_process > 0.1:
                        print(f"[Worker] ⚠️  Gap before process_fn: {t_before_fn - t_before_process:.3f}s", flush=True)
                    
                    # 调用 process_frame（在线程池中执行，不阻塞事件循环）
                    await loop.run_in_executor(None, server.process_frame, meta, model_ctx)
                    t_after_process = time.time()
                    
                    # 检查 process_fn 执行时间
                    fn_duration = t_after_process - t_before_fn
                    if fn_duration > 5.0:
                        print(f"[Worker] ⚠️  process_frame took {fn_duration:.3f}s (this is the blocking operation!)", flush=True)
                    
                    # ========== 时间追踪4：完成 ==========
                    process_time = t_after_process - t_before_process
                    total_time = t_after_process - t_before_get
                    
                    # 如果有大的时间差，输出警告
                    if queue_wait_in_worker > 1.0:
                        print(f"[Worker] ⚠️  in_q.get() blocked for {queue_wait_in_worker:.3f}s", flush=True)
                    if gap_since_last_frame > 5.0:
                        print(f"[Worker] ⚠️  Gap since last frame: {gap_since_last_frame:.3f}s", flush=True)
                    
                    # 使用 run_in_executor 将同步 put 操作异步化
                    await loop.run_in_executor(None, out_q.put, (identity, b"OK"))
                    id_str = identity[:8].hex() if isinstance(identity, bytes) and len(identity) >= 8 else str(identity)[:16]
                    # print(f"[Worker] ✓ 已发送响应 OK (identity={id_str}...)", flush=True)
                except Exception as e:
                    print(f"[Worker] process error task={meta.get('task')}: {e}", flush=True)
                    traceback.print_exc()
                    await loop.run_in_executor(None, out_q.put, (identity, b"ERR"))
                    id_str = identity[:8].hex() if isinstance(identity, bytes) and len(identity) >= 8 else str(identity)[:16]
                    print(f"[Worker] ✓ 已发送响应 ERR (identity={id_str}...)", flush=True)
        finally:
            # 清理资源
            try:
                if hasattr(server, 'db') and server.db:
                    await server.db.close()
                    print(f"[Worker] 数据库连接池已关闭", flush=True)
            except Exception as e:
                print(f"[Worker] 关闭数据库连接池失败: {e}", flush=True)
            
            print(f"[Worker] Worker 进程退出", flush=True)

class WorkerPool:
    def __init__(self, out_q: mp.Queue, server_cls):
        self.workers = {}
        self.out_q = out_q
        self.server_cls = server_cls  # 传递类而不是 bound method
    def get(self, key: str) -> Worker:
        w = self.workers.get(key)
        if w is None:
            w = Worker(self.out_q, self.server_cls)
            self.workers[key] = w
        return w
    
    def shutdown(self):
        """优雅关闭所有 worker"""
        for w in self.workers.values():
            w.stop()
        for w in self.workers.values():
            w.join(timeout=5.0)
        self.workers.clear()

class BaseServer:
    def __init__(self, addr: str = None):
        """初始化服务器
        
        Args:
            addr: IPC 地址，如果不提供则使用环境变量 PY_ZMQ_ADDR 或默认值
        """
        if addr:
            self.addr = addr
        else:
            self.addr = os.getenv("PY_ZMQ_ADDR", "ipc:///tmp/py_ai.ipc")
    def process_frame(self, meta: dict, model_ctx: dict = None):
        raise NotImplementedError
    @staticmethod
    def init_model_context():
        """默认的模型上下文初始化，子类可重写"""
        return {}
    def select_worker_key(self, meta: dict) -> str:
        return "default"
    def serve(self):
        import zmq
        ctx = zmq.Context()
        router = ctx.socket(zmq.ROUTER)
        try:
            router.bind(self.addr)
        except Exception:
            if self.addr.startswith("ipc://"):
                try:
                    os.unlink(self.addr.replace("ipc://", ""))
                except Exception:
                    pass
                router.bind(self.addr)
        print(f"{self.__class__.__name__} start @ {self.addr}", flush=True)
        out_q = mp.Queue()
        pool = WorkerPool(out_q, self.__class__)  # 传递类而不是 bound method
        poller = zmq.Poller()
        poller.register(router, zmq.POLLIN)
        pending_count = 0  # 队列中待处理的请求数
        last_monitor_time = time.time()
        last_heartbeat_time = time.time()  # 心跳时间
        request_count = 0
        
        try:
            while True:
                t_loop_start = time.time()
                
                # 心跳：每5秒打印一次，证明主循环没有卡住
                if t_loop_start - last_heartbeat_time > 1.0:
                    print(f"[SERVER-HEARTBEAT] Main loop alive, pending={pending_count}, requests={request_count}, "
                          f"since_last_heartbeat={t_loop_start - last_heartbeat_time:.3f}s", flush=True)
                    last_heartbeat_time = t_loop_start
                
                t_poll_start = time.time()
                events = dict(poller.poll(1))
                t_poll_end = time.time()
                poll_duration = t_poll_end - t_poll_start
                
                # 如果 poll 时间异常，记录日志
                if poll_duration > 1.5:  # poll(1) 应该最多 1 秒
                    print(f"[SERVER] ⚠️  poll() took {poll_duration:.3f}s (expected <=1.0s)", flush=True)
                
                if router in events:
                    t_recv_start = time.time()
                    frames = router.recv_multipart()
                    t_recv_end = time.time()
                    recv_duration = t_recv_end - t_recv_start
                    
                    if recv_duration > 0.1:
                        print(f"[SERVER] ⚠️  recv_multipart() took {recv_duration:.3f}s", flush=True)
                    
                    if len(frames) < 2:
                        continue
                    identity, payload = frames[0], frames[-1]
                    try:
                        t_json_start = time.time()
                        meta = json.loads(payload.decode("utf-8"))
                        meta["timestamp"] = time.time()
                        t_json_end = time.time()
                        json_duration = t_json_end - t_json_start
                        
                        if json_duration > 0.1:
                            print(f"[SERVER] ⚠️  json.loads() took {json_duration:.3f}s", flush=True)
                    except Exception:
                        router.send_multipart([identity, b"", b"ERR"])
                        continue

                    # 健康检查由主进程直接响应，不能排入可能正繁忙或尚未
                    # 完成模型初始化的推理队列。这样 ai_stream 可以在任意
                    # 启动顺序下快速发现服务上线。
                    if meta.get("task") == "__health__":
                        router.send_multipart([identity, b"", b"OK"])
                        continue

                    #print(f"{self.__class__.__name__} recv task={meta.get('task')}", flush=True)
                    # print(f"[AI] Received task: {meta.get('task')}", flush=True)
                    key = self.select_worker_key(meta)
                    w = pool.get(key)
                    
                    # ⚠️ 非阻塞put，如果队列满（Worker忙），丢弃旧帧，插入新帧
                    put_success = False
                    try:
                        # 尝试非阻塞put
                        w.in_q.put_nowait((identity, meta))
                        put_success = True
                    except:
                        # 队列满，丢弃队列中的旧帧，插入新帧
                        try:
                            old_identity, _old_meta = w.in_q.get_nowait()  # 丢弃旧帧
                            print(f"[Server] Dropped old frame to make room for new frame", flush=True)
                            try:
                                router.send_multipart([old_identity, b"", b"BUSY"])
                            except Exception:
                                pass
                            pending_count = max(0, pending_count - 1)
                        except:
                            pass
                        try:
                            w.in_q.put_nowait((identity, meta))  # 插入新帧
                            put_success = True
                        except:
                            print(f"[Server] ⚠️  Failed to put frame, sending BUSY", flush=True)
                            router.send_multipart([identity, b"", b"BUSY"])
                    
                    # 只有成功入队，才增加计数
                    if put_success:
                        pending_count += 1
                        request_count += 1
                    
                processed = 0
                while not out_q.empty() and processed < 10:  # 最多一次处理 10 个结果
                    try:
                        identity, res = out_q.get_nowait()
                        router.send_multipart([identity, b"", res])
                        pending_count = max(0, pending_count - 1)
                        processed += 1
                    except Exception:
                        break
                
                # 检测单次循环耗时
                t_loop_end = time.time()
                loop_duration = t_loop_end - t_loop_start
                if loop_duration > 2.0:  # 单次循环超过2秒
                    print(f"[SERVER] ⚠️ ⚠️ ⚠️  CRITICAL: Main loop iteration took {loop_duration:.3f}s! "
                          f"(poll={poll_duration:.3f}s) This is blocking all requests!", flush=True)
                
                # 定期监控队列积压和吞吐量
                current_time = time.time()
                if current_time - last_monitor_time >= 10.0:  # 每10秒监控一次
                    qps = request_count / 10.0
                    print(f"[{self.__class__.__name__}] Status: pending={pending_count}, QPS={qps:.2f}", flush=True)
                    last_monitor_time = current_time
                    request_count = 0
                    
                    # 警告：队列积压严重
                    if pending_count > 20:
                        print(f"[{self.__class__.__name__}] ⚠️  WARNING: {pending_count} requests pending! Worker may be stuck!", flush=True)
        except KeyboardInterrupt:
            print(f"[{self.__class__.__name__}] 收到中断信号，开始优雅关闭...", flush=True)
        except Exception as e:
            print(f"[{self.__class__.__name__}] 发生异常: {e}", flush=True)
            traceback.print_exc()
        finally:
            # 优雅关闭所有 worker
            print(f"[{self.__class__.__name__}] 正在关闭 worker pool...", flush=True)
            pool.shutdown()
            print(f"[{self.__class__.__name__}] Worker pool 已关闭", flush=True)
