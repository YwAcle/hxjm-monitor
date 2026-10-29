# CLIP-ReID 特征服务

独立 FastAPI 服务。单图接口返回归一化的行人特征；轨迹接口将同一行人的多帧
分别经过 CLIP-ReID，再对归一化特征平均并再次归一化。当前不连接数据库，
截图接口用 YOLOv8n 检测行人：单人直接裁剪提特征，多人返回坐标供 Agent
等待用户选择。服务不跟踪、不判断身份，也不修改旧服务。

## 文件与复用

- `server.py`：配置、模型初始化、截图检测裁剪、批量提取、池化、接口和独立启动入口。
- `requirements.txt`：新增 API 依赖，含测试客户端 httpx。
- `tests/test_api.py`：合成图片与注入的测试提取器，验证接口和资源限制。
- `tests/test_features.py`：数值验证，以及按开关启用的真实模型验证与基本性能测量。

通过独立模块命名空间导入 `../reid/CLIP-ReID/model/make_model.py` 的
`make_model()`、`../reid/CLIP-ReID/config` 和原 `ModifiedResNet` 实现，
加载 `../reid/config/cnn_base.yml` 与
`../reid/weights/MSMT17_clipreid_RN50_120.pth`。
现有权重已经包含完整 `image_encoder` 和 BN 参数，因此构建时只替换该独立
模块的基础权重初始化入口，不调用旧下载函数；随后严格加载所有推理参数。
训练分类头和文本参数不参与图片推理。第一版仅支持 RN50，无需 CLIP 基础权重，
不修改或实例化旧 `ReidServer`。
截图检测直接使用 `ultralytics.YOLO` 和现有 `../reid/weights/yolov8n.pt`，
不导入旧视频服务、跟踪器或数据库模块。

## 启动

要求 Python 3.10+，复用兼容旧 ReID 的 torch、torchvision、numpy、Pillow、
timm、yacs、ftfy、regex、tqdm 和 ultralytics 环境。模型和资源通过文件位置定位，不依赖启动目录。

以下命令从仓库根目录执行。依赖安装到个人工作区，避免更改共享 Conda 环境：

```bash
conda activate reid
python -m pip install --target .run/reid-feature-deps -r python/reid_feature_service/requirements.txt
PYTHONPATH="$PWD/.run/reid-feature-deps" REID_FEATURE_PORT=28024 \
  python python/reid_feature_service/server.py
```

默认监听 `127.0.0.1:28024`，通过 `REID_FEATURE_HOST` / `REID_FEATURE_PORT` 覆盖。
与 Java `18480`、检测服务 `28014`、旧 ReID 的 ZeroMQ IPC 独立。
本服务没有加入现有启停脚本。用 Ctrl+C 关闭。
**只运行一个 Uvicorn worker，不启用 reload**，避免重复加载模型。
启动完成后访问 `http://127.0.0.1:28024/docs` 进行交互调用。

如果 VS Code 通过 Remote SSH 连接开发服务器，本地浏览器的 `127.0.0.1` 指的是
自己的电脑。先在 VS Code「端口 / Ports」面板选择「转发端口」，输入 `28024`，
然后打开该行显示的本地地址并追加 `/docs`。若本地端口被占用，VS Code 可能分配
其他端口，以面板显示的地址为准。也可以在自己电脑的终端建立 SSH 转发：

```bash
ssh -N -L 28024:127.0.0.1:28024 <用户名>@<开发服务器地址>
```

服务需要先启动，并等待日志出现 `Application startup complete`；仅完成安装或
运行测试不会持续启动服务。如果浏览器能连接但文档页空白，先检查 `/health` 和
`/openapi.json`，Swagger 页面还需要浏览器能加载其 CDN 上的 JS/CSS 资源。

配置变量：

| 环境变量 | 默认值 | 含义 |
| --- | --- | --- |
| `REID_FEATURE_WEIGHTS` | 旧 RN50 权重路径 | 本地 ReID 权重 |
| `REID_FEATURE_CONFIG` | 旧 `cnn_base.yml` | 模型配置 |
| `REID_FEATURE_YOLO_WEIGHTS` | 旧 `weights/yolov8n.pt` | 本地行人检测权重，不自动下载 |
| `REID_FEATURE_DETECTION_CONFIDENCE` | 0.4 | 行人检测置信度阈值，范围 (0, 1] |
| `REID_FEATURE_DEVICE` | `auto` | `cpu`、`cuda`、`cuda:0` 等；auto 检测 CUDA 并尝试初始化，失败时使用 CPU |
| `REID_FEATURE_CPU_THREADS` | 2 | CPU 推理的 PyTorch 线程数，避免大量线程竞争 |
| `REID_FEATURE_MAX_IMAGE_BYTES` | 10485760 | 单图片最大 10 MiB |
| `REID_FEATURE_MAX_REQUEST_BYTES` | 33554432 | 完整请求最大 32 MiB，含 multipart 包装 |
| `REID_FEATURE_MAX_PIXELS` | 16777216 | 单图最大解码像素数 |
| `REID_FEATURE_MAX_FRAMES` | 32 | 轨迹请求最大图片数 |
| `REID_FEATURE_SAMPLE_FRAMES` | 8 | 均匀选取最多 8 帧参与推理，须不大于 MAX_FRAMES |
| `REID_FEATURE_MAX_REQUESTS` | 8 | 正在上传、等待、执行的 POST 请求总上限 |

模型在启动时加载、校验参数并预热一次。所有推理串行放在同一专用线程；
等待请求有上限，满时返回 503。请求取消不会终止已经运行的 PyTorch 推理，
该工作完成前仍占用请求名额。此版本没有强制终止卡住推理的子进程监督机制。
路径和运行设备配置错误、模型缺失或关键权重不匹配会导致启动失败。
YOLO 在首次调用截图接口时加载，之后常驻复用；首次调用会多出加载和首次推理开销。
检测与 ReID 共用所选设备及专用线程，单图、轨迹接口不会初始化或调用 YOLO。
YOLO 配置缓存默认位于仓库 `.run/reid-feature-cache`，可用 `YOLO_CONFIG_DIR` 覆盖。
检测模型加载失败时截图接口返回 503，已有单图、轨迹接口仍可使用。

## 接口

支持静态 JPEG、PNG、WebP，先校正 EXIF 方向再转 RGB，不接收视频文件。
截图走 `person-crops`；已裁剪的人像走 `image-features`；同一轨迹的多帧人像走
`tracklet-features`。后两个接口不检测人数或校验身份。
优先上传干净原图，避免检测框和文字覆盖目标身体。

### `POST /v1/reid/person-crops`：对话截图入口

`multipart/form-data`：`file` 为截图，`metadata` 为可选 JSON 字符串。
仅检测 person 类别，推理尺寸 640，NMS IoU 为 0.5，检测阈值默认 0.4。
最多返回 100 个有效行人框；超过时返回 422 `TOO_MANY_PEOPLE`，提示缩小截图区域。

```bash
curl -sS http://127.0.0.1:28024/v1/reid/person-crops \
  -F 'file=@/path/to/screenshot.jpg' \
  -F 'metadata={"request_id":"query-001","source_asset_id":"screenshot-001"}'
```

三个正常分支均返回 HTTP 200，Agent 应根据 `status` 处理：

| `status` | 含义 | `feature` | Agent 下一步 |
| --- | --- | --- | --- |
| `extracted` | 检测到一个行人 | 已裁剪提取的完整特征响应 | 直接使用 `feature.embedding` |
| `selection_required` | 检测到多个行人 | `null`，尚未运行 ReID | 展示候选，等待用户选择 |
| `no_person` | 未检测到行人 | `null` | 提示重传或手动框选，不直接用整张图提特征 |

多人响应示例：

```json
{
  "request_id": "query-001",
  "status": "selection_required",
  "image_width": 1920,
  "image_height": 1080,
  "coordinate_system": "xyxy_pixels_exif_corrected",
  "person_count": 2,
  "selection_required": true,
  "candidates": [
    {"candidate_id": "1", "bbox": [120, 80, 300, 600], "confidence": 0.93},
    {"candidate_id": "2", "bbox": [500, 100, 680, 620], "confidence": 0.89}
  ],
  "selected_candidate_id": null,
  "feature": null
}
```

单人响应结构相同，`person_count=1`、`selection_required=false`、
`selected_candidate_id="1"`，`feature` 是下文所示的单图完整响应，额外包含 `crop`。
候选按左边界 x、上边界 y 等坐标排序，从 `"1"` 开始编号，仅在本次检测中有效，
不是人员身份或轨迹 ID。置信度是检测置信度，不是身份相似度。

坐标以 **EXIF 方向校正后的原图**为基准，左上角为原点，格式为整型像素
`[x1,y1,x2,y2]`，右、下边界不包含在裁剪范围内，可以等于原图宽、高。
前端画框时需要按图片显示尺寸缩放坐标，提交选择时仍传原始像素坐标。
本接口只返回坐标和单人情况下的特征，不返回裁剪图片、Base64 或图片 URL。

**Agent 多轮衔接约定：**

1. Agent 保存原始截图文件、`source_asset_id` 和本次 `candidates`，在对话框中展示编号或画框。
2. 收到 `selection_required` 后等待用户明确选择，不擅自选择最大框或最高置信度框。
3. 用户选中候选 `"2"` 时，Agent 取该候选的 `bbox`，将**同一张原始截图**和框提交给
   `image-features`，不需要再次调用截图检测接口。
4. 取得特征后再进入后续检索流程。服务不保存截图或待选择状态，也不会主动回调 Agent；
   不能只提交 `candidate_id` / `request_id` 取特征。不同截图的候选信息不能混用。

例如用户选择上例中的第二个人：

```bash
curl -sS http://127.0.0.1:28024/v1/reid/image-features \
  -F 'file=@/path/to/screenshot.jpg' \
  -F 'bbox=[500,100,680,620]' \
  -F 'metadata={"request_id":"query-001","source_asset_id":"screenshot-001"}'
```

Agent 后端保留向量供后续检索使用，不需要将 3072 个特征数值发送给大模型。

### `POST /v1/reid/image-features`

`multipart/form-data`：`file` 是一张图片；`metadata` 是可选 JSON 字符串。
不传 `bbox` 时，按已有方式提取整张单人人像的特征。
可选 `bbox` 是 JSON 字符串 `[x1,y1,x2,y2]`，用于对原截图中的指定人像先裁剪再提取特征；
该路径不调用 YOLO，也支持前端手动框选。坐标必须是整数、面积为正且完全在校正后的原图内，
非法框返回 422 `INVALID_BBOX`。使用 `bbox` 时响应额外返回：

```json
{
  "crop": {
    "bbox": [500, 100, 680, 620],
    "image_width": 1920,
    "image_height": 1080,
    "coordinate_system": "xyxy_pixels_exif_corrected"
  }
}
```

```bash
curl -sS http://127.0.0.1:28024/v1/reid/image-features \
  -F 'file=@/path/to/person.jpg' \
  -F 'metadata={"request_id":"query-001","source_asset_id":"image-001"}'
```

### `POST /v1/reid/tracklet-features`

重复的 `files` 字段是同一人的多帧裁剪图，**按时间顺序上传**。
可选 `metadata.frame_ids` 与文件顺序一一对应，字符串 ID 必须唯一。
服务按上传顺序均匀采样，不根据文件名或时间自动排序。
所有上传图片都要能成功解码，任何一张损坏都会拒绝整次请求，包括未选中的帧。

```bash
curl -sS http://127.0.0.1:28024/v1/reid/tracklet-features \
  -F 'files=@/path/to/frame1.jpg' \
  -F 'files=@/path/to/frame2.jpg' \
  -F 'metadata={"camera_id":"camera_1","stream_session_id":"session-1","track_id":"7","segment_id":"seg-1","frame_ids":["f1","f2"]}'
```

三个 POST 接口的 `metadata` 均支持：`request_id`、`source_asset_id`、`camera_id`、
`stream_session_id`、`track_id`、`segment_id`、`frame_ids`。ID 都是字符串，
拒绝未知字段；metadata 不超过 8 KiB。未传 request_id 时自动生成；未传 frame_ids
时返回从 `"0"` 开始的图片索引。当前这些来源字段可选，后续入库集成可再收紧要求。

响应示意（embedding 省略，实际返回 3072 个数）：

```json
{
  "request_id": "query-001",
  "feature_type": "image",
  "embedding": [0.01, 0.02],
  "embedding_dim": 3072,
  "feature_space_id": "clipreid-rn50-<版本摘要>",
  "normalized": true,
  "dtype": "float32",
  "aggregation": "none",
  "input_count": 1,
  "used_count": 1,
  "selected_frame_ids": ["0"],
  "source": {"source_asset_id": "image-001"},
  "persistence_status": "not_requested"
}
```

轨迹结果的 `feature_type` 为 `tracklet`，`aggregation` 为 `mean_l2_v1`。
`dtype` 指向量计算精度，HTTP 中是 JSON 数值数组。
`feature_space_id` 根据权重内容、旧模型代码、配置和预处理版本计算，单图和轨迹
共享；后续只能直接比较同一特征空间的向量。池化策略另用 aggregation 标记。
特征仅通过本次响应返回，服务不持久化，也不承诺之后能按 request_id 取回。

### `GET /health`

就绪时 HTTP 200，返回 ready、model、embedding_dim、feature_space_id、device。
额外的 `detector_loaded` 表示 YOLO 是否已完成构造，不代表截图检测准确率。
模型启动/预热完成前 Uvicorn 不开始接收请求，关闭过程中 ready 为 false。

错误：HTTP 413 表示字节/像素限制，415 表示不支持的图片格式，422 表示图片或参数
无效，503 表示繁忙/未就绪或检测模型不可用（`DETECTOR_UNAVAILABLE`），500 表示推理异常。业务错误结构为
`{"detail":{"error_code":"INVALID_IMAGE","message":"..."}}`；缺失表单字段等
请求结构错误使用 FastAPI 原生 422 格式。

## 验证

不依赖真实行人、轨迹样本或数据库。使用合成图片验证接口、采样、异常输入、
请求容量、健康检查响应，以及特征和池化的数学性质：

新增测试覆盖单人实际裁剪区域、多人等待与选框续接、无人、EXIF 坐标、框校验、
检测框取整/裁边/排序、模型复用及检测器不可用时旧接口的可用性。

```bash
PYTHONPATH="$PWD/.run/reid-feature-deps:$PWD/python" \
  python -B -m unittest discover -s python/reid_feature_service/tests -v
```

启用已有真实模型，验证 3072 维、单位范数、重复和批量一致性、与旧模型加载/前向
一致性、缺失推理权重被拒绝、真实 API 并发及单图/轨迹结果一致性：

```bash
PYTHONPATH="$PWD/.run/reid-feature-deps:$PWD/python" \
  REID_FEATURE_TEST_MODEL=1 REID_FEATURE_DEVICE=cpu \
  python -B -m unittest discover -s python/reid_feature_service/tests -v
```

如需同时验证真实 YOLO 和截图全流程，在上述真实模型命令中再设置
`REID_FEATURE_TEST_DETECTOR=1`。该测试使用已安装 Ultralytics 自带的 `assets/bus.jpg`，
验证多人返回坐标、选框特征与手动裁剪特征一致、单人自动提取和空白图无人分支，
不下载样本，不需要轨迹数据，也不评估人员检索准确率。

真实模型测试还输出 1/4/8 帧 API 各 3 次的中位和最大耗时；CUDA 模式额外报告
PyTorch 峰值已分配显存。它是基本性能检查，正式容量评估需要部署设备与持续负载。
默认 CPU 测试及服务使用 2 个计算线程，可通过 CPU_THREADS 配置调整。
合成图片的测试不能说明人员检索准确率；“以图找轨迹”、池化收益和匹配阈值
等待以后取得有身份标注的样本再验证。
