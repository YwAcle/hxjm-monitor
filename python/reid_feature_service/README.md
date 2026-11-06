# CLIP-ReID / Chinese-CLIP 特征服务

独立 FastAPI 服务。图片接口使用 CLIP-ReID：单图返回归一化的 3072 维行人特征；
轨迹接口将同一行人的多帧分别提取，再对归一化特征平均并再次归一化。文字检索
接口使用 Chinese-CLIP ViT-B/16，把中文描述与登记图编码到独立的 512 维空间。
两套特征空间由不同的 `feature_space_id` 标识，向量不能跨空间比较或混写。
当前不连接数据库，截图接口用 YOLOv8n 检测行人：单人直接裁剪提特征，多人返回
坐标供 Agent 等待用户选择。服务不跟踪、不判断身份，也不修改旧服务。

## 文件与复用

- `server.py`：配置、两套模型初始化、截图检测裁剪、批量提取、池化、文字/图片编码、接口和独立启动入口。
- `requirements.txt`：新增 API 依赖，含测试客户端 httpx 与 Chinese-CLIP 所需的 transformers。
- `tests/test_api.py`：合成图片与注入的 CLIP-ReID 测试提取器，验证图片接口和资源限制。
- `tests/test_text_api.py`：注入的 Chinese-CLIP 测试提取器，验证文字接口、契约字段和故障隔离。
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
timm、yacs、ftfy、regex、tqdm、ultralytics 和 transformers 环境。Chinese-CLIP
代码按 `reid` 环境的 transformers 5.5.x 接口编写，真实权重推理可用下方开关单独验证。
模型和资源通过文件位置定位，不依赖启动目录。

以下命令从仓库根目录执行。依赖安装到个人工作区，避免更改共享 Conda 环境：

```bash
conda activate reid
python -m pip install --target .run/reid-feature-deps -r python/reid_feature_service/requirements.txt
PYTHONPATH="$PWD/.run/reid-feature-deps" REID_FEATURE_PORT=28024 \
  python python/reid_feature_service/server.py

cd /data/nfs_storage/hxjm-zwd

REID_FEATURE_HOST=0.0.0.0 \
REID_FEATURE_PORT=28024 \
REID_FEATURE_WEIGHTS=/data/nfs_storage/hxjm_datas/models/reid/MSMT17_clipreid_RN50_120.pth \
REID_FEATURE_CONFIG=/data/nfs_storage/hxjm-zwd/python/reid/config/cnn_base.yml \
REID_FEATURE_YOLO_WEIGHTS=/data/nfs_storage/hxjm_datas/models/reid/yolov8n.pt \
REID_FEATURE_TEXT_MODEL=/data/nfs_storage/hxjm_datas/models/reid/chinese-clip-vit-base-patch16 \
REID_FEATURE_DEVICE=cuda:1 \
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
| `REID_FEATURE_TEXT_MODEL` | `/data/nfs_storage/hxjm_datas/models/reid/chinese-clip-vit-base-patch16` | Chinese-CLIP 本地模型目录，只读加载，不联网下载 |
| `REID_FEATURE_TEXT_MAX_CHARS` | 200 | 文字描述字符上限，超出返回 422 `TEXT_TOO_LONG` |
| `REID_FEATURE_TEXT_MAX_TOKENS` | 0 | 文字 token 上限；0 使用模型位置编码上限（本模型为 512），设置后只能调小 |
| `REID_FEATURE_TEXT_SPACE_ID` | 空 | 可选，固定文字特征空间 ID；留空时按模型文件摘要生成 |
| `REID_FEATURE_TEXT_CONTRACT_ID` | 空 | 可选，固定文本契约 ID；留空时为 `<feature_space_id>-text-v1` |
| `REID_FEATURE_DETECTION_CONFIDENCE` | 0.4 | 行人检测置信度阈值，范围 (0, 1] |
| `REID_FEATURE_DEVICE` | `auto` | `cpu`、`cuda`、`cuda:0` 等；auto 检测 CUDA 并尝试初始化，失败时使用 CPU |
| `REID_FEATURE_CPU_THREADS` | 2 | CPU 推理的 PyTorch 线程数，避免大量线程竞争 |
| `REID_FEATURE_MAX_IMAGE_BYTES` | 10485760 | 单图片最大 10 MiB |
| `REID_FEATURE_MAX_REQUEST_BYTES` | 33554432 | 完整请求最大 32 MiB，含 multipart 包装 |
| `REID_FEATURE_MAX_PIXELS` | 16777216 | 单图最大解码像素数 |
| `REID_FEATURE_MAX_FRAMES` | 32 | 轨迹请求最大图片数 |
| `REID_FEATURE_SAMPLE_FRAMES` | 8 | 均匀选取最多 8 帧参与推理，须不大于 MAX_FRAMES |
| `REID_FEATURE_MAX_REQUESTS` | 8 | 正在上传、等待、执行的 POST 请求总上限 |

CLIP-ReID 模型在启动时加载、校验参数并预热一次；Chinese-CLIP 也在启动时从
`REID_FEATURE_TEXT_MODEL` 加载到同一设备，先编码一段固定文本和一张合成图片，
确认两个投影输出维度一致、均为有限单位向量后才把 `text_reid.ready` 置为 true。
该探测只验证结构与特征空间一致，不代表检索准确率。Chinese-CLIP 加载失败不会
中止进程：`/health` 的 `text_reid.ready=false` 并附带 `error`，文字接口返回 503，
已有图片接口继续可用。两个模型的推理都串行放在同一专用线程；等待请求有上限，
满时返回 503。请求取消不会终止已经运行的 PyTorch 推理，该工作完成前仍占用请求
名额。此版本没有强制终止卡住推理的子进程监督机制。
CLIP-ReID 的路径、运行设备或关键权重配置错误仍会导致启动失败。
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

### `POST /v1/reid/text-features`：文字描述编码

`application/json` 请求体：

```json
{"text": "穿黑色外套、背双肩包的男子", "language": "auto", "template_id": "", "metadata": {}}
```

`text` 必填；`language` 默认 `auto`，按文本内容返回 `zh` / `en` / `unknown`，
显式传入其他值则原样返回；`template_id` 保留字段，当前只校验长度；`metadata`
原样回显到响应的 `source`。文字先去首尾空白，空文本返回 422 `TEXT_EMPTY`，
超过 `REID_FEATURE_TEXT_MAX_CHARS` 或模型 token 上限返回 422 `TEXT_TOO_LONG`。
服务**不截断文本**，响应中的 `truncated` 恒为 `false`。

```bash
curl -sS http://127.0.0.1:28024/v1/reid/text-features \
  -H 'Content-Type: application/json' \
  -d '{"text":"穿黑色外套的男子","language":"auto","template_id":"","metadata":{}}'
```

```json
{
  "request_id": "9c1f...",
  "feature_type": "text",
  "model_profile": "chinese_clip_text_reid",
  "embedding": [0.01, 0.02],
  "embedding_dim": 512,
  "feature_space_id": "chinese-clip-vit-b16-<摘要>",
  "text_contract_id": "chinese-clip-vit-b16-<摘要>-text-v1",
  "normalized": true,
  "dtype": "float32",
  "truncated": false,
  "language": "zh",
  "token_count": 12,
  "text_chars": 12,
  "source": {},
  "persistence_status": "not_requested"
}
```

`embedding` 实际返回 512 个数，示例省略。`token_count` 含分词器自动添加的
首尾特殊 token，因此可能大于 `text_chars`。

### `POST /v1/reid/text-reid-image-features`：登记图编码

`multipart/form-data`，字段 `file` 为一张 JPEG/PNG/WebP 登记图。服务用
Chinese-CLIP 的图片编码器把图映射到与文字相同的 512 维空间，供 Agent 按文本
描述排序登记库。图片会先校正 EXIF 并转 RGB，限制与图片接口相同。

```bash
curl -sS http://127.0.0.1:28024/v1/reid/text-reid-image-features \
  -F 'file=@/path/to/registered_person.jpg'
```

响应与文字接口结构一致，`feature_type` 为 `image`，不含 `text_contract_id`、
`truncated`、`language` 等文本字段，额外返回 `image_width` / `image_height`。
该接口不运行 YOLO，也不会退回 CLIP-ReID；两个接口的向量只能与同一
`feature_space_id` 的向量比较。

错误码：模型未就绪或加载失败返回 503 `TEXT_MODEL_NOT_READY`；文本为空返回
422 `TEXT_EMPTY`；文本超长返回 422 `TEXT_TOO_LONG`；推理异常返回 500
`TEXT_EXTRACTION_FAILED`；图片校验沿用 `INVALID_IMAGE` / `IMAGE_TOO_LARGE` /
`UNSUPPORTED_IMAGE_FORMAT`。

### `GET /health`

就绪时 HTTP 200，返回 ready、model、embedding_dim、feature_space_id、device。
额外的 `detector_loaded` 表示 YOLO 是否已完成构造，不代表截图检测准确率。
`text_reid` 块描述 Chinese-CLIP：`ready`、`alignment_verified`、
`feature_space_id`、`embedding_dim`、`text_contract_id`、`model`、`device`；
未就绪时附 `error`（`disabled` 表示启动时未启用，`initialization_failed` 表示
加载失败，详见服务日志）。整体 `ready` 只反映 CLIP-ReID 图片模型，文字模型
失败不会把 HTTP 状态改为 503，避免影响已有图片链路；调用文字接口前应检查
`text_reid.ready` 与 `alignment_verified` 同时为 true。
模型启动/预热完成前 Uvicorn 不开始接收请求，关闭过程中 ready 为 false。

错误：HTTP 413 表示字节/像素限制，415 表示不支持的图片格式，422 表示图片或参数
无效，503 表示繁忙/未就绪、检测模型不可用（`DETECTOR_UNAVAILABLE`）或文字模型
不可用（`TEXT_MODEL_NOT_READY`），500 表示推理异常。业务错误结构为
`{"detail":{"error_code":"INVALID_IMAGE","message":"..."}}`；缺失表单字段等
请求结构错误使用 FastAPI 原生 422 格式。

## 验证

不依赖真实行人、轨迹样本或数据库。使用合成图片验证接口、采样、异常输入、
请求容量、健康检查响应，以及特征和池化的数学性质：

新增测试覆盖单人实际裁剪区域、多人等待与选框续接、无人、EXIF 坐标、框校验、
检测框取整/裁边/排序、模型复用及检测器不可用时旧接口的可用性。文字测试使用
注入的假 Chinese-CLIP 提取器，验证健康块字段、文字/图片响应契约、语言识别、
空文本与超长文本、特征空间隔离，以及文字模型加载失败时图片接口仍可用。

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

启用共享目录中的真实 Chinese-CLIP，验证 512 维、单位范数、文本与图片同空间、
特征空间/契约 ID 和超长拒绝（会加载约 719 MB 权重，默认跳过）：

```bash
PYTHONPATH="$PWD/python" \
  REID_FEATURE_TEST_TEXT_MODEL=1 REID_FEATURE_DEVICE=cpu \
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
