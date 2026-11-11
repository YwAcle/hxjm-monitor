# ReID 特征服务接口规范（供推理服务方实现）

本文是工作台（hxjm_agent）对 ReID 推理服务的接口要求。工作台按 YOLO 检测服务的接入方式对接：算法服务只交换"图片 + 选择 → 事实"，不感知摄像头、任务、模型或下一步动作。本文中 **MUST / SHOULD / MAY** 按 RFC 语义使用，MUST 项是接入验收的硬条件。

服务方可以按本文重写接口，也可以写一层很薄的转换层把现有实现包装成下述契约（见第 11 节），内部推理代码不必改动。

## 1. 职责边界

**服务负责**：模型加载与校验、图片解码与裁剪、特征提取、相似度计算、特征空间与版本标识、繁忙与失败语义。

**服务不负责**：目标检测、跟踪、跨帧身份状态、摄像头与任务概念、结果落库、历史登记库检索、相似度阈值判定、调度下一步、调用大模型、保存或回传原始特征。

工作台侧已有点目标检测（YOLO11n，COCO 类别含 `person`），因此 **主链路不需要服务自带行人检测**。

服务对外提供**两套互相隔离的特征空间**，向量不能跨空间比较、不能共用阈值：

| 空间 | 模型 | 维度 | 用途 |
| --- | --- | --- | --- |
| 图像空间 | CLIP-ReID（行人） | 3072 | 图 vs 图，跨帧/跨镜同人核验 |
| 文字空间 | Chinese-CLIP（图文对齐） | 512 | 中文描述 vs 图，按描述筛选候选 |

## 2. 接口总览

| 方法 | 路径 | 用途 | 工作台是否调用 |
| --- | --- | --- | --- |
| `GET` | `/api/health` | 存活与两套模型就绪 | 人工检查（可选） |
| `POST` | `/api/analysis/reid/compare` | **图 vs 多个图**，返回图像空间相似度 | **是** |
| `POST` | `/api/analysis/reid/compare-text` | **中文描述 vs 多个图**，返回文字空间相似度 | **是** |
| `POST` | `/api/analysis/reid/features` | 返回单张裁剪图的图像特征 | 否（v1 不使用，供算法方离线实验） |

命名与检测服务保持一致（`/api/analysis/...`、`/api/health`），便于工作台用同一套约定接入后续算法。

## 3. 通用约定

### 3.1 传输格式

- 请求与响应均为 `application/json; charset=utf-8`。
- 图片一律为 **data URL 字符串**：`data:image/jpeg;base64,<JPEG 的 Base64>`。只接受 JPEG。
- **MUST NOT** 接受文件路径、URL、`file://` 或多段上传（multipart）。工作台只持有内存中的 JPEG 字节。
- 单张图片字符串 ≤ 3,000,000 字符；单次请求体 ≤ 32 MiB；单图解码后 ≤ 16,000,000 像素。
- 请求体 MUST 拒绝未知字段，返回 422。

### 3.2 坐标

- `box` 为 `[left, top, right, bottom]`，**归一化到 0～1**，浮点，相对于所提供图片解码后的像素矩阵。
- MUST 满足 `0 ≤ left < right ≤ 1`、`0 ≤ top < bottom ≤ 1`。
- 服务自行换算像素：`x = round(v * W)`、`y = round(v * H)`，右/下边界不含。

示例：图片 1920×1080，`box = [0.10, 0.22, 0.36, 0.81]` → 像素 `[192, 238, 691, 875]`，裁出 499×637 的人像。

- **MUST NOT 应用 EXIF 旋转**。若图片带非 1 的 Orientation 标记，返回 422 而不是静默旋转——旋转会改变调用方使用的坐标基准。
- 裁剪 MUST 精确等于该框，不加任何 padding。预处理（resize、均值方差等）必须固定并在 `feature_space_id` 中体现。
- 裁剪后宽、高均须 ≥ 8 像素且面积 ≥ 256 像素，否则返回 422 `BOX_TOO_SMALL`。例如同一张 1920×1080 图上 `box = [0.400, 0.500, 0.403, 0.510]` → 像素 `[768, 540, 774, 551]`，仅 6×11，必须拒绝。

### 3.3 错误格式

- 业务错误统一为 `{"detail": "<可直接展示给操作者的中文说明>"}`，`detail` 是**字符串**，不是对象。
- 代码类短标识放在说明开头，例如 `{"detail": "INVALID_IMAGE：仅支持 JPEG，且不超过 1600 万像素"}`。
- 请求结构错误（缺字段、字段类型错误）允许使用框架原生 422 格式。

| HTTP | 含义 | 调用方处理 |
| --- | --- | --- |
| 200 | 成功（**允许相似度低于任何阈值**，这不是失败） | 使用结果 |
| 413 | 请求体或图片超过上限 | 不重试，记录失败 |
| 415 | 不支持的图片格式 | 不重试 |
| 422 | 输入非法（图片、框、文本、参数） | 不重试 |
| 429 | **繁忙**：已有推理在跑 | 可稍后重试，不得自动重试风暴 |
| 503 | 模型未就绪或不可用 | 视为服务故障 |
| 500 | 推理异常 | 视为服务故障 |

判别要点：**繁忙一律 429，不要用 503**；503 只表示服务本身不能用。

### 3.4 并发

- 同一时刻最多 1 个在途推理请求；超出上限立刻返回 429，不排队、不自动重试、不建队列。
- 单次请求的处理时间硬上限 60 秒，超时由服务自己中断并返回 500。
- 单 Uvicorn worker，禁用 `--reload`，避免重复加载模型。

### 3.5 结果自证

每个成功响应 MUST 带：`model`、`model_sha256`、`feature_space_id`、`embedding_dim`、`metric`、`duration_ms`、`cold_start`（本次是否包含首次加载/预热）。工作台会把这几项原样记入任务证据，用于事后复核，不参与业务判断。

## 4. `GET /api/health`

就绪返回 200：

```json
{
  "service": "reid",
  "ready": true,
  "model": "MSMT17_clipreid_RN50_120.pth",
  "model_sha256": "<64 位摘要>",
  "feature_space_id": "clipreid-rn50-<64 位摘要>",
  "embedding_dim": 3072,
  "device": "cuda:1",
  "text_reid": {
    "ready": true,
    "model": "chinese-clip-vit-base-patch16",
    "model_sha256": "<64 位摘要>",
    "feature_space_id": "fs-<64 位摘要>",
    "text_contract_id": "fs-<64 位摘要>-text-v1",
    "embedding_dim": 512,
    "device": "cuda:1"
  }
}
```

- 顶层 `ready` 只表示图像空间可用；`text_reid.ready` 单独表示文字空间可用。任一为 false 时 MUST 在同一层级附 `error` 字符串。
- 健康检查 MUST 不触发推理、不加载未加载的模型。
- `service` 字段值固定为 `reid`（工作台用它识别服务身份，同检测服务的 `yolo`）。
- 文字模型加载失败不得让整个进程退出：`text_reid.ready=false`，`compare-text` 返回 503，`compare` 继续可用。

## 5. `POST /api/analysis/reid/compare`（图 vs 图）

### 5.1 请求

```json
{
  "request_id": "task-7f3a-camera_1-obs12-c2",
  "query": {
    "image": "data:image/jpeg;base64,<JPEG>",
    "box": [0.10, 0.22, 0.36, 0.81]
  },
  "targets": [
    {"id": "c1", "image": "data:image/jpeg;base64,<JPEG>", "box": [0.52, 0.18, 0.71, 0.79]},
    {"id": "c3", "image": "data:image/jpeg;base64,<JPEG>", "box": [0.05, 0.30, 0.19, 0.88]}
  ]
}
```

- `request_id`：字符串，≤ 96 字符，服务仅回显与写日志，不建索引、不持久化。
- `targets`：1～8 项；`id` 为调用方提供的字符串（≤ 32 字符，本次请求内唯一），服务 MUST 原样回显。
- `targets` 的图片可以是同一张（多个候选来自同一帧）——服务不得假设图片互不相同。
- 同一请求内所有图片与框使用同一 `feature_space_id`，由服务保证。

### 5.2 响应（200）

示例数值仅示意字段形状，不是任何真实模型的测量结果：

```json
{
  "request_id": "task-7f3a-camera_1-obs12-c2",
  "metric": "cosine",
  "model": "MSMT17_clipreid_RN50_120.pth",
  "model_sha256": "<64 位摘要>",
  "feature_space_id": "clipreid-rn50-<64 位摘要>",
  "embedding_dim": 3072,
  "duration_ms": 187.4,
  "cold_start": false,
  "matches": [
    {"id": "c1", "similarity": 0.831204},
    {"id": "c3", "similarity": 0.104918}
  ]
}
```

- `similarity`：**余弦相似度**，范围 `[-1, 1]`，保留 6 位小数。它是相似度，**不是概率、不是同一人概率**，不得命名为 `score`、`confidence`、`prob`。
- `matches` MUST 覆盖每个请求中的 `id`，顺序不要求与请求一致，但调用方按 `id` 匹配。
- **MUST NOT 返回特征向量**。3072 维数值不进入 HTTP 响应；如算法方需要调试，另开只在开发环境启用的接口，不并入本契约。
- **MUST NOT 返回 `is_same` / `same_person` 之类的布尔结论，也不返回推荐阈值**。阈值属于场景标定，由调用方负责，服务不预设。

### 5.3 语义要求（可测）

1. **自比**：`query` 与某个 `target` 的图片与框完全相同 → `|similarity - 1| ≤ 1e-6`。
2. **对称**：交换 query 与 target → `|s_ab - s_ba| ≤ 1e-5`。
3. **确定性**：同一请求重复调用（同一设备、无 TTA、无随机翻转）→ 结果差 ≤ 1e-6。
4. **批量一致**：同一目标单独请求 vs 放在批量里，结果差 ≤ 1e-6。
5. **顺序无关**：调换 `targets` 顺序不改变对应 id 的相似度。

## 6. `POST /api/analysis/reid/compare-text`（文字 vs 图）

用于"只有中文描述、没有参照图"的场景，例如"找穿黑色外套、背双肩包的男子"。服务把文本编码一次，再把每个候选裁剪图编码到同一 512 维空间，返回余弦相似度。

### 6.1 请求

```json
{
  "request_id": "task-7f3a-camera_3-obs15",
  "query": {
    "text": "穿黑色外套、背双肩包的男子",
    "language": "auto"
  },
  "targets": [
    {"id": "c1", "image": "data:image/jpeg;base64,<JPEG>", "box": [0.05, 0.30, 0.19, 0.88]},
    {"id": "c2", "image": "data:image/jpeg;base64,<JPEG>", "box": [0.52, 0.18, 0.71, 0.79]}
  ]
}
```

- `query.text`：必填字符串，先去首尾空白；空文本返回 422 `TEXT_EMPTY`。
- 文本上限 200 字符，超过返回 422 `TEXT_TOO_LONG`，**不得截断**。
- `query.language`：只接受 `auto`、`zh`、`en`、`unknown`；默认 `auto`；`auto` 时由服务判定并在响应回显。
- `targets`：格式、数量、`id` 回显、坐标与裁剪规则**完全同第 5 节**。
- 图像侧 MUST 用 **Chinese-CLIP 的图片编码器**，不得用 CLIP-ReID 的 3072 维向量代替，也不得更改为其它模型。

### 6.2 响应（200）

示例数值仅示意字段形状，不是任何真实模型的测量结果：

```json
{
  "request_id": "task-7f3a-camera_3-obs15",
  "metric": "cosine",
  "query_type": "text",
  "model": "chinese-clip-vit-base-patch16",
  "model_sha256": "<64 位摘要>",
  "feature_space_id": "fs-<64 位摘要>",
  "text_contract_id": "fs-<64 位摘要>-text-v1",
  "embedding_dim": 512,
  "language": "zh",
  "duration_ms": 210.5,
  "cold_start": false,
  "matches": [
    {"id": "c1", "similarity": 0.314502},
    {"id": "c2", "similarity": 0.087731}
  ]
}
```

- `similarity`、`matches` 的语义与约束同第 5.2 节：余弦相似度、6 位小数、按 `id` 覆盖全部 target、不返回向量、不返回布尔结论与阈值。
- `feature_space_id` MUST 是文字空间的 ID（`fs-` 加完整 64 位摘要），且与图像空间的 ID 不同。
- `text_contract_id` MUST 与 `/api/health` 中 `text_reid.text_contract_id` 一致。
- `model_sha256` 为实际加载的权重文件摘要；若权重是目录（多文件），取主权重文件并在服务文档中注明文件名。
- 该空间是通用图文对齐模型，**相似度绝对值通常显著低于图像空间**，两个空间的数值不可比较、不可共用阈值。调用方只在本空间内做候选排序。

### 6.3 语义要求（可测）

1. **确定性**：同一文本 + 同一裁剪图重复调用 → 结果差 ≤ 1e-6。
2. **批量一致**：单独调用 vs 批量调用 → 结果差 ≤ 1e-6；调换 `targets` 顺序不改变结果。
3. **空间隔离**：响应中的 `feature_space_id` 与 `compare` 的必须不同；服务 MUST NOT 交叉使用两套模型。
4. **不截断**：输入文本原样编码，响应不提供 `truncated` 之类的静默截断标记。
5. **低分不是失败**：相似度低属正常结果，不得转成 4xx/5xx，也不得返回"未找到该人"之类的结论。

## 7. `POST /api/analysis/reid/features`（可选，工作台 v1 不调用）

用途仅为算法方离线实验与批量评估：`image`（data URL）+ `box`，返回 `embedding`（MUST 为 L2 单位向量）、`embedding_dim`、`feature_space_id`、`normalized: true`、`model`、`model_sha256`、`duration_ms`。

工作台不调用该接口，因此其字段调整不影响接入验收。

## 8. 模型与资源

- 权重 MUST 从本地路径加载，**请求处理中不得下载或联网**；缺失或校验失败时启动失败并打印路径。
- 启动阶段完成加载、参数校验与一次预热；预热完成前不监听端口（或 `/api/health` 返回 503 `ready=false`）。
- 设备通过部署配置指定（`cpu` / `cuda:N`），**不得**由请求参数覆盖；调用方也不能传模型名、权重路径、阈值、设备。
- 两套模型共用同一推理线程时串行执行；等待请求有上限，满时立即 429。文字模型加载失败不得影响图像链路。
- MUST NOT 做测试时增强（翻转、多尺度投票），否则破坏确定性。
- 日志记录 `request_id`、目标数量、文本长度、耗时、错误码；**不得**记录图片字节、原始文本或特征值。

## 9. 明确不做的事

- 不做行人检测：调用方已用 YOLO 的 `person` 候选；服务收到的每个框都视为一个人。
- 不做多人选择交互：`selection_required`、候选编号、等待用户选择都不属于本契约。
- 不存特征、不建登记库、不提供按 id 取回特征；不连数据库。文字比较只针对调用方本次提供的候选，**不检索历史登记库**。
- 不判断身份、不返回阈值结论、不判断"目标是否离开画面"。
- 不感知摄像头、观察编号、任务与会话。

## 10. 验收清单

服务方交付时需附以下证据（工作台按此验收，缺一项即不通过）：

1. **契约测试**（可用注入的假模型）：两个 `compare*` 的字段、错误码、413/415/422/429/503 分支、`id` 回显、大小上限、坐标越界与 `BOX_TOO_SMALL`、EXIF 拒绝、未知字段拒绝；`compare-text` 另需空文本、超长文本、语言回显。
2. **数学性质测试**：第 5.3 与 6.3 节全部条目，包括两套空间的隔离检查。
3. **真实模型测试**：真实权重下的同人/不同人样本对比，以及中文描述与明显符合/明显不符合候选的对比。给出所用样本、`model_sha256`、`feature_space_id`、单次耗时（p50 / p95），以及相似度的**原始分布**。不得给出"准确率 95%"这类没有标注与协议支撑的数字；有标注数据时才报告评测集合与协议。
4. **性能**：`compare` 与 `compare-text` 各自在 `targets=1`、`targets=8` 下的 p50 / p95 耗时，GPU 型号，峰值显存。
5. **启动与故障**：权重缺失、设备不可用、推理异常，以及文字模型加载失败时 `compare` 仍可用的实际日志与返回码。
6. **样例请求/响应**：三个接口各两条可直接复制的 `curl` 与真实响应（图片可替换为脱敏样本）。

## 11. 可选：先用转换层实现

若服务内部实现暂时不动，可以写一个约 200 行的薄适配进程：接收本文契约的 JSON，转成现有内部调用，再按第 5.2 / 6.2 节返回结果。要求：

- 转换层本身不持有状态、不缓存结论、不改语义；
- 繁忙/错误映射必须严格按第 3.3 节（尤其 429 与 503 的区分）；
- 一旦内部接口稳定，应把这层删掉、直接实现本契约，避免长期双份维护。

## 12. 与现有实现的差异对照

| 现状 | 规范要求 | 原因 |
| --- | --- | --- |
| `multipart/form-data` + 文件字段 | JSON + `data:image/jpeg;base64,` | 工作台只持有内存字节；与检测服务契约统一 |
| `bbox` 为原始像素、EXIF 校正后坐标 | `box` 归一化 0～1，禁止 EXIF 旋转 | 与工作台检测结果（归一化框）同一坐标语言，避免双方各算一遍 |
| 主接口自带 YOLO 检测行人并返回候选 | 不检测，只接收"图 + 框" | 工作台已有检测与候选编号体系，避免两套候选 |
| 返回 `embedding`（3072 维） | 返回 `similarity`，向量不出服务 | 3072 个数值没有业务含义，且会让每次比对多一次误差来源 |
| 文本接口分 `text-features` 与 `text-reid-image-features` 两次调用、由调用方算余弦 | 合并为 `compare-text` 一次返回 | 与 `compare` 同构，调用方只有一套形状；少一次 HTTP 与一次向量序列化 |
| 文本检索依赖 `feature` 表登记库 | 只比较本次提供的候选 | 当前帧内按描述筛选不需要登记库 |
| `detail` 是对象 `{error_code,message}` | `detail` 为字符串 | 调用方按字符串透传给模型/日志 |
| 繁忙返回 503 | 繁忙返回 429 | 区分"重试可能成功"与"服务不可用" |
| `/v1/reid/*` | `/api/analysis/reid/*`、`/api/health` | 与既有算法服务命名一致 |

## 13. 调用方将如何使用（便于自测）

工作台一次任务中会有两种用法：

**A. 有参照图**（跨帧/跨镜同人核验）

1. 用已有检测结果拿到各路候选的归一化框；
2. 取该次观察的 JPEG，base64 成 data URL；
3. 调 `compare`，把 `candidate_id` 填进 `targets[].id`；
4. 只把 `similarity`、`model_sha256`、`feature_space_id`、`embedding_dim`、耗时记入任务证据，向量不落库。

**B. 只有文字描述**

1. 同一帧的检测候选作为 `targets`；
2. 把用户原话（可精炼为外观描述）作为 `query.text`；
3. 调 `compare-text`，按返回的相似度排序，再由模型结合画面决定是否采用；
4. 结果进入证据的方式同 A。

服务方自测时，用三段 `curl` 覆盖即可：

```bash
curl -sS http://127.0.0.1:28024/api/health

curl -sS http://127.0.0.1:28024/api/analysis/reid/compare \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"demo-1",
       "query":{"image":"data:image/jpeg;base64,<A>","box":[0.10,0.22,0.36,0.81]},
       "targets":[{"id":"t1","image":"data:image/jpeg;base64,<B>","box":[0.52,0.18,0.71,0.79]}]}'

curl -sS http://127.0.0.1:28024/api/analysis/reid/compare-text \
  -H 'Content-Type: application/json' \
  -d '{"request_id":"demo-2",
       "query":{"text":"穿黑色外套的男子","language":"auto"},
       "targets":[{"id":"t1","image":"data:image/jpeg;base64,<B>","box":[0.52,0.18,0.71,0.79]}]}'
```

## 14. 变更规则

- 字段只增不改；删除或改语义必须更换路径（如 `/api/analysis/reid/compare-v2`）并在响应中保留旧字段一个版本周期。
- 权重、预处理或模型代码变化时 `feature_space_id` 必须随之变化；`model_sha256` 必须反映实际加载的文件。两套空间各自独立版本化。
- 服务地址由部署配置决定，调用方不得通过请求参数指定服务端文件、权重或设备。