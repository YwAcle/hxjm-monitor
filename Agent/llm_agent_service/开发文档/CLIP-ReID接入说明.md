# CLIP-ReID 单人图片检索接入

本次接入 `GET /health` 与 multipart `POST /v1/reid/image-features`。地址默认 `http://100.127.237.7:28024`。单人裁剪图保持原流程；截图检测和多人选择参见《截图找人与多人选择接入.md》。暂不调用轨迹接口。文字检索通过同一服务的 Chinese-CLIP 文本接口完成，见[登记库主动行人检索](登记库主动行人检索最小接入.md)。

## 配置和运行

根目录 `.env`：

```dotenv
REID_FEATURE_BASE_URL=http://100.127.237.7:28024
REID_TIMEOUT_S=30
# 可选：固定健康检查返回的完整版本标识
# REID_FEATURE_SPACE_ID=clipreid-rn50-<版本摘要>
```

启动脚本会传递环境变量，Python 启动入口解析以上配置。修改后需重启 Agent 才能生效；实现不自动重启服务。图片检索仅使用 CLIP-ReID，不再提供本地推理或通用 JSON 特征后端。旧的 `REID_BACKEND`、`REID_MODEL_PATH`、`REID_EMBEDDING_URL` 和 `REID_EMBEDDING_MODEL` 环境变量不再读取，可以从本地配置移除；对应的旧命令行参数也不再支持。服务不可达时明确返回工具失败，不自动混用另一模型的检索结果。

ReID 由 Agent 后端直连，HTTP 客户端禁用系统代理；无需浏览器访问或配置 CORS。远程服务默认监听 127.0.0.1，必须监听 Agent 可达的地址或通过转发开放该端口。开发时不要仅凭远程本机能打开 `/docs` 就认为 Agent 可访问。

## 特征兼容策略

旧库的 `embedding_model=CLIP-ReID-ResNet50` 不能证明与新服务的 `feature_space_id` 相同。因此最小接入先不比较旧向量：查询图片与有效登记照片都通过新接口生成3072维特征，归一化后按余弦相似度排序。健康检查每次查询一次；校验 ready、维度及版本，随后各图片响应必须保持同一特征空间。跨请求服务升级后重新生成登记特征。

登记特征按特征空间、人员 ID 和图片摘要缓存在 Agent 进程内。登记图片更换、停用或模型版本更换后旧缓存被淘汰。首次查询需串行请求查询图和登记图，可能耗时较长；重启 Agent 后缓存需重建。后续可先确认旧向量兼容性，再复用数据库特征以降低冷启动成本。本次不修改数据库结构和已有向量，不写入人员身份关系。

任一有效登记图片的远程提取失败会中止本次检索，避免把服务错误当作“没有匹配”。无效或缺失登记图片跳过并体现在 skipped_count。原候选格式继续沿用，method 为 remote_clipreid，embedding_model 为服务特征空间标识。特征数组不发送给大模型或前端。

## 验证与前端操作

只检查远端连通性：

```bash
curl --noproxy '*' --connect-timeout 5 --max-time 10 http://100.127.237.7:28024/health
```

无需聊天模型的真实登记库检索验证（默认取首张登记图作自身检索，输出去除图片）：

```bash
/data1/userhome/va/miniconda3/envs/monitor/bin/python scripts/verify_local_reid.py
```

聊天窗口同时上传单人图并输入：“用这张图片在登记库找相似行人，返回前3个候选。”继续使用现有 search_pedestrians_by_image 工具。普通 /chat 返回 data.candidates；SSE /chat/stream 通过 result 事件返回候选卡片数据。

已知限制：此前定位的 Agent 60秒总预算问题尚未在本次接入中修改，慢模型决策和首次登记特征构建都可能使完整聊天超时。独立验证脚本可以先确认特征服务和检索链路。服务没有部署在当前仓库，本次不修改远端监听和启停方式。
