# HXJM Git Worktree 协同开发使用手册

> 协作方式更新（2026-10-29，v0.2）：本文件保留旧工作区／worktree方式的历史操作说明。后续开发采用独立账号、独立clone仓库和按需求创建的功能分支，以[协同开发流程](COLLABORATION_WORKFLOW.md)为准；旧目录迁移前仍需保留未交付改动。本文中的旧工作区启动说明不代表新账号下启动配置已验证。

本手册适用于当前协作方式：每个人在自己的 worktree 目录和开发分支中开发，由集成人员在 `/data/nfs_storage/hxjm` 的 `main` 分支合并、验证，并将 `main` 推送到远程仓库。

远程名称：`origin`。远程地址：`https://gitee.com/wo_di_chao_chao/HXJM.git`。

> 路径以当前服务器为例。命令需要逐步执行并检查结果；出现错误或冲突时，先处理再继续。文中的 `path/to/file`、`提交ID` 等是占位符，需要替换为实际值。本文只描述操作方法，不会自动更改分支或远程仓库。

## 目录

1. [当前目录和分支](#1-当前目录和分支)
2. [理解 worktree、分支和远程](#2-理解-worktree分支和远程)
3. [团队约定](#3-团队约定)
4. [首次检查与个人配置](#4-首次检查与个人配置)
5. [当前已有工作树如何开始使用](#5-当前已有工作树如何开始使用)
6. [开发人员日常流程](#6-开发人员日常流程)
7. [个人分支推送与拉取](#7-个人分支推送与拉取)
8. [在 main 合并并推送](#8-在-main-合并并推送)
9. [冲突处理](#9-冲突处理)
10. [保存未完成的工作](#10-保存未完成的工作)
11. [添加、移动和删除工作树](#11-添加移动和删除工作树)
12. [完整协作示例](#12-完整协作示例)
13. [常见问题](#13-常见问题)
14. [撤销和恢复](#14-撤销和恢复)
15. [VS Code 使用方式](#15-vs-code-使用方式)
16. [运行环境与忽略文件](#16-运行环境与忽略文件)
17. [常用命令速查](#17-常用命令速查)
18. [交付和集成检查清单](#18-交付和集成检查清单)

## 1. 当前目录和分支

当前工作树信息：

```text
/data/nfs_storage/hxjm      f9d5396 [main]
/home/guest/hxjm-wsc  3d89f1c [dev/wsc]
/home/guest/hxjm-wyf  e687e06 [dev/wyf]
```

| 使用者 / 用途 | 工作目录 | 本地分支 | 主要操作 |
| --- | --- | --- | --- |
| 集成人员 | `/data/nfs_storage/hxjm` | `main` | 更新主分支、合并、验证、推送 `origin/main` |
| WSC | `/home/guest/hxjm-wsc` | `dev/wsc` | 开发、提交、同步主分支 |
| WYF | `/home/guest/hxjm-wyf` | `dev/wyf` | 开发、提交、同步主分支 |

查看实时状态：

```bash
git -C /data/nfs_storage/hxjm worktree list
git -C /data/nfs_storage/hxjm branch -vv
git -C /data/nfs_storage/hxjm remote -v
```

手册编写时（2026-10-10）检查到的本地状态如下。这只是快照，`origin/*` 记录以最近一次 fetch 为准，不代表已实时查询远程服务器：

| 分支 | 当前上游 | 本地状态 | 使用前应处理 |
| --- | --- | --- | --- |
| `main` | `origin/main` | 与本地记录的远程主分支一致 | fetch 后检查是否需要更新 |
| `dev/wsc` | `origin/main` | 落后 6 个提交；工作目录中 `README.md` 有未提交修改 | 先保存修改，再同步主分支；不要依赖无参数 pull / push |
| `dev/wyf` | `origin/dev/wyf` | 本地领先 1 个提交、落后 1 个提交 | fetch 后先合并远程个人分支，再同步主分支 |

仓库还存在 `wsc`、`wyf`、`tzh`、`zwd` 等分支。`wsc` 与 `dev/wsc`、`wyf` 与 `dev/wyf` 是不同分支；当前工作树使用的是 `dev/wsc` 和 `dev/wyf`，合并时必须写对完整名称。旧分支可能有尚未集成的提交，不要因名称相似直接删除。

## 2. 理解 worktree、分支和远程

### 2.1 一个仓库，多个工作目录

`git worktree` 让同一个本地 Git 仓库同时检出多个分支。每个目录有自己的文件、当前分支、暂存区和未提交修改，可以分别打开编辑器开发。

工作树共享 Git 对象、提交历史、本地分支、远程跟踪引用和 stash。一个人在自己的目录提交后，其他工作树立即能通过对应本地分支看到该提交，无需先推送再拉取。文件变化仍需要合并到另一个分支，才会出现在另一个工作目录中。

```text
远程 Gitee 仓库
  origin/main
       ↑ main 由集成人员推送
       |
本地共享仓库
  /data/nfs_storage/hxjm      → main
                            ↑ 合并 dev/wsc、dev/wyf
  /home/guest/hxjm-wsc  → dev/wsc
  /home/guest/hxjm-wyf  → dev/wyf
```

同一个本地分支通常只能在一个 worktree 中检出。因此，在个人目录不要执行 `git switch main`，需要操作 main 时进入 `/data/nfs_storage/hxjm`。

### 2.2 本地分支、远程跟踪分支和上游

| 名称 / 操作 | 含义 |
| --- | --- |
| `main` | 本地主分支，由主工作目录检出 |
| `dev/wsc`、`dev/wyf` | 本地个人开发分支 |
| `origin/main` | 本地保存的远程 main 状态，fetch 后更新 |
| `origin/dev/wyf` | 本地保存的远程 WYF 开发分支状态 |
| 上游分支 | 无参数 pull、部分 push 行为所依据的跟踪配置 |
| `git fetch origin` | 下载远程提交、更新远程跟踪引用，不自动合并到当前分支 |
| `git merge origin/main` | 把已 fetch 的远程主分支提交合并到当前分支 |
| `git pull --ff-only origin main` | 获取远程 main，并尝试快进当前分支；无法快进时停止 |
| `git push origin main` | 把本地 main 推送到远程 main，不是自动选择当前分支 |

**同步个人分支自身的远程提交**和**同步主分支代码**是两个不同操作。WYF 需要分别合并 `origin/dev/wyf` 和 `origin/main`，只执行 `git pull` 不一定能得到主分支更新。

### 2.3 同一台服务器与不同电脑

本文三个目录属于同一个本地仓库，集成人员可以直接执行 `git merge dev/wsc`。

如果成员在另一台电脑独立 clone，分支和提交不会在本地共享。对方必须先推送个人分支，集成人员 fetch 后再合并 `origin/dev/wsc`。远程仓库不会保存服务器上的 worktree 目录，也不会因 pull 自动创建这些目录。

## 3. 团队约定

1. **个人开发在自己的目录完成。** WSC 使用 `hxjm-wsc`，WYF 使用 `hxjm-wyf`；main 工作目录用于集成。
2. **main 由约定的集成人员串行操作。** 同一时段只允许一人操作 `/data/nfs_storage/hxjm`，提前协调集成时间。worktree 不提供多人编辑同一工作目录的隔离。
3. **日常采用 merge 同步。** 长期个人分支不随意 rebase，main 不强制推送，避免改写他人已使用的历史。
4. **操作前查看目录、分支和工作区。** 合并和拉取前先提交或保存未完成修改。
5. **提交后再交付。** 未提交文件不会随分支合并。交付时说明分支、提交 ID、变更和验证结果。
6. **避免混入未完成工作。** merge 会合并该分支所有尚未进入 main 的提交；含多个未完成任务时，使用单独任务分支交付。
7. **推送时写清远程和分支。** 个人推送 `origin dev/wsc` 或 `origin dev/wyf`；main 推送由集成人员在主目录执行。
8. **先验证再发布。** 按涉及模块进行测试、构建或运行检查；同时修改同一处逻辑时，提前约定接口和文件责任。

个人分支上传有两种约定，团队统一选择：

| 约定 | 个人开发分支 | main 集成 |
| --- | --- | --- |
| 仅 main 上传远程 | 个人只在本地提交，同服务器即可交付 | 直接合并本地个人分支并推送 main |
| main 发布，个人分支也备份到远程 | 可推送 `dev/<姓名>`，便于备份或跨电脑协作 | 验证集成结果后推送 main |

本文支持两种约定。个人推送步骤仅在允许远程备份或跨电脑协作时执行；无论选择哪种，都不要从个人目录代替集成人员推送 main。

## 4. 首次检查与个人配置

### 4.1 检查当前目录和分支

WSC 示例：

```bash
cd /home/guest/hxjm-wsc
pwd
git branch --show-current
git status
git branch -vv
git remote -v
```

确认当前分支为 `dev/wsc`。WYF 使用 `/home/guest/hxjm-wyf` 和 `dev/wyf`。

### 4.2 配置提交身份

先检查身份：

```bash
git var GIT_AUTHOR_IDENT
git config --show-origin --get user.name
git config --show-origin --get user.email
```

多人共用服务器上的 `guest` 系统账号时，`git config --global` 会影响该账号的其他仓库，普通 `git config --local` 会影响同仓库所有工作树。不要轮流通过这两种方式覆盖彼此身份。

支持 worktree 配置的 Git 版本，可由集成人员在主目录一次性开启：

```bash
git -C /data/nfs_storage/hxjm config extensions.worktreeConfig true
```

各成员再在自己的目录配置，换成真实姓名、邮箱：

```bash
cd /home/guest/hxjm-wsc
git config --worktree user.name "WSC 的姓名"
git config --worktree user.email "wsc@example.com"
git var GIT_AUTHOR_IDENT
```

WYF 和集成人员也分别配置。所有访问此仓库的 Git 客户端应支持该扩展；普通仓库通常可以直接启用，若已有特殊 `core.worktree` 或 `core.bare` 配置，应先由维护者检查迁移要求。

如果客户端无法使用 worktree 配置，可在创建提交的命令中临时指定身份：

```bash
git -c user.name="WSC 的姓名" -c user.email="wsc@example.com" commit -m "feat: 实现某项功能"
```

临时配置只对该条命令生效。merge、revert 等也可能创建提交，采用该方案时同样需要这两个 `-c` 参数。

### 4.3 配置远程认证

使用有仓库权限的 Gitee 账号，按提示完成 HTTPS 认证或配置 SSH。提交身份和远程认证是两回事，`user.name` / `user.email` 不会授予推送权限。

不要将密码、令牌写入远程 URL、代码或提交记录。main 如有远程保护策略，由有权限的集成人员遵守仓库审批流程操作。

## 5. 当前已有工作树如何开始使用

本节针对第 1 节的初始状态。先重新检查；状态已变化时按实际输出处理。

### 5.1 WSC：先保存 README 修改，再同步主分支

```bash
cd /home/guest/hxjm-wsc
git status
git diff -- README.md
```

如果修改已完成且需要提交：

```bash
git add README.md
git diff --cached
git commit -m "docs: 更新项目说明"
```

尚未完成时按第 10 节 stash 保存。确认工作区干净后：

```bash
git fetch origin
git merge origin/main
```

冲突按第 9 节处理；此前 stash 的修改，合并完成后按第 10 节恢复。

`dev/wsc` 当前跟踪 `origin/main`，无参数 pull 会从主分支拉取；当前 `push.default=simple` 下，无参数 push 通常因本地分支名与上游名不同而拒绝。不要依赖这些隐含行为。

如果团队允许个人分支上传，完成同步、检查提交后执行：

```bash
git push -u origin dev/wsc
git branch -vv
```

成功后上游设为 `origin/dev/wsc`。若远程已有 `dev/wsc` 且拒绝推送，先 fetch、合并 `origin/dev/wsc`，再重试。仅 main 上传时跳过个人推送，后续使用明确的 fetch / merge 命令同步。

### 5.2 WYF：先处理个人分支分叉，再同步主分支

```bash
cd /home/guest/hxjm-wyf
git status
git fetch origin
git log --oneline --graph --decorate --max-count=20 dev/wyf origin/dev/wyf origin/main
```

工作区干净后，先整合远程个人分支的提交：

```bash
git merge origin/dev/wyf
```

有冲突先处理并完成合并，再执行：

```bash
git merge origin/main
```

验证完成后，如允许个人上传：

```bash
git push -u origin dev/wyf
```

本地与远程各有新提交时，`git pull --ff-only origin dev/wyf` 会停止，这是正常保护行为。这里采用 merge 保留双方历史，无需强制推送。

## 6. 开发人员日常流程

以 WSC 为例，WYF 替换为自己的目录和分支。

### 6.1 开始开发前同步

```bash
cd /home/guest/hxjm-wsc
git branch --show-current
git status
```

有未提交修改时先提交或 stash。工作区干净后：

```bash
git fetch origin
```

如果个人分支已在远程存在，且其他电脑或成员可能更新了它，先执行：

```bash
git merge origin/dev/wsc
```

远程没有该分支时跳过此步，再同步主分支：

```bash
git merge origin/main
git status
```

合并可能快进、产生合并提交，或报告已是最新。任何冲突都应处理完再开始新开发。

同服务器上，如需同步集成人员已完成并允许使用、但尚未推送的本地 main，可协调后执行 `git merge main`。日常优先使用 `origin/main`，以已发布的主分支为基准。

### 6.2 修改、检查、暂存和提交

完成一个可验证的小任务后：

```bash
git status
git diff
git add path/to/file1 path/to/file2
git diff --cached
git diff --cached --check
git commit -m "feat: 增加某项功能"
git status
```

占位路径需替换为真实文件。`git diff --cached` 检查将提交的内容，`--check` 检查空白错误，功能正确性仍需运行对应模块的测试或构建。

建议按文件暂存，也可 `git add -p` 按片段暂存。确认所有变更都应提交时再使用 `git add -A`，避免混入临时配置和不相关修改。

提交说明示例：

```text
feat: 增加视频流状态展示
fix: 修复断线后无法重连的问题
docs: 更新接口文档
refactor: 整理异常报告处理逻辑
```

### 6.3 交付集成

交付前提交需要合并的修改，再次同步主分支并验证：

```bash
git fetch origin
git merge origin/main
git status
git log --oneline origin/main..dev/wsc
git diff --stat origin/main...dev/wsc
git rev-parse --short HEAD
```

两点 log 查看个人分支尚未进入远程 main 的提交；三点 diff 从共同祖先查看个人分支的变更，便于审查。

如允许远程备份，可推送个人分支，再向集成人员说明：

```text
分支：dev/wsc
待合并提交：实际提交 ID
变更：视频流状态展示
验证：实际完成的测试、构建或运行检查
依赖：是否需先合并其他分支、是否涉及配置或数据库变化
```

同服务器上不推送个人分支也可交付。为保证集成结果可复现，集成人员开始审查后，暂停向本次交付分支追加提交，直到集成完成；继续工作时可另建任务分支。

### 6.4 main 发布后同步回来

```bash
cd /home/guest/hxjm-wsc
git status
git fetch origin
git merge origin/main
```

仍需先保证工作区干净。WYF 同样同步，下一轮开发便包含其他成员新合入的代码。

## 7. 个人分支推送与拉取

### 7.1 首次和后续推送

允许个人上传时，WSC 在自己的目录执行：

```bash
git push -u origin dev/wsc
```

WYF 在自己的目录执行：

```bash
git push -u origin dev/wyf
```

`-u` 设置对应分支上游。后续仍建议显式指定远程和分支，例如：

```bash
git push origin dev/wsc
```

### 7.2 拉取个人分支自身的远程更新

工作区干净、远程个人分支存在时，WSC 可执行：

```bash
git pull --ff-only origin dev/wsc
```

该命令适用于能够快进的情况。本地、远程都增加了提交而拒绝时，先检查差异，再 merge：

```bash
git fetch origin
git log --oneline --left-right dev/wsc...origin/dev/wsc
git merge origin/dev/wsc
```

三点 log 显示双方独有提交，左侧 `<` 属于本地，右侧 `>` 属于远程。之后按需 `git merge origin/main` 同步主分支。

### 7.3 推送被拒绝：non-fast-forward

表示远程有本地尚未包含的提交，个人分支可这样处理：

```bash
git fetch origin
git merge origin/dev/wsc
```

解决冲突、验证后重试 `git push origin dev/wsc`。不要用 `git push --force` 覆盖他人提交。main 遇到同类问题见第 8.4 节。

## 8. 在 main 合并并推送

仅由集成人员在 `/data/nfs_storage/hxjm` 操作。确认无人同时修改主工作目录，开发者已冻结本次交付提交。

### 8.1 更新并检查 main

```bash
cd /data/nfs_storage/hxjm
git branch --show-current
git status
git fetch origin
git merge --ff-only origin/main
```

确认分支为 main、工作区干净。fetch 加快进 merge 明确拆开获取和更新；也可使用 `git pull --ff-only origin main`。

若无法快进，检查是否已有合法的本地待推送集成提交，或远程 main 也产生了新提交：

```bash
git log --oneline --left-right main...origin/main
git log --oneline --graph --decorate --max-count=30 main origin/main
```

本地 main 已包含远程 main、本地独有提交均为确认的集成结果时，可以继续审查；双方真正分叉时按第 8.4 节整合。不要自动 reset 丢弃本地提交。

### 8.2 审查待合并内容

同服务器直接检查本地个人分支：

```bash
git log --oneline main..dev/wsc
git diff --stat main...dev/wsc
git diff main...dev/wsc
```

确认变更范围、作者、接口变化和验证结果。合并会包含所有已提交且尚未进入 main 的内容，不包含未提交文件。

跨电脑协作时，先要求开发者推送，再 fetch，将本节的 `dev/wsc` 替换为 `origin/dev/wsc`。不要把可能过期的本地分支误当作已更新的远程分支。

### 8.3 逐个合并、验证、推送

先合并 WSC：

```bash
git merge --no-ff dev/wsc -m "merge: 合并 WSC 本次开发"
```

`--no-ff` 在有新内容时保留独立合并提交，便于追踪交付批次。有冲突时按第 9 节解决。WSC 合并并验证通过后，如果还要合并 WYF，先重新检查 `main..dev/wyf` 和差异，再执行：

```bash
git merge --no-ff dev/wyf -m "merge: 合并 WYF 本次开发"
```

按模块测试、构建或启动验证。第二个分支即使已同步过 main，也可能与刚合入的第一个分支冲突；无文本冲突也可能存在逻辑冲突。跨电脑交付对应合并 `origin/dev/wsc`、`origin/dev/wyf`。一次只合并一个分支，便于定位问题。

所有集成结果验证通过后：

```bash
git status
git diff --check origin/main main
git log --oneline origin/main..main
git push origin main
```

`git diff --check origin/main main` 检查本次待发布差异的空白错误，不替代测试。push 成功后通知开发者同步 main；失败时本地集成尚未发布。

确认本地 main 与最新远程记录一致：

```bash
git fetch origin
git rev-list --left-right --count main...origin/main
```

输出 `0 0` 表示双方无独有提交；如果远程在期间继续更新，按实际差异处理。

### 8.4 main 推送失败或与远程分叉

远程 main 在本地集成期间增加了提交时：

```bash
git fetch origin
git log --oneline --left-right main...origin/main
```

确认远程变更合理后整合：

```bash
git merge origin/main
```

解决冲突，重新验证受影响模块，再执行 `git push origin main`。这里通过 merge 保留合法双方历史；远程被意外重写或含异常提交时，先由维护者查明原因。

## 9. 冲突处理

冲突可能出现在同步 main、合并个人分支、同步远程个人分支和恢复 stash 时。以下以 merge 冲突为例。

### 9.1 查看冲突文件

```bash
git status
git diff --name-only --diff-filter=U
```

Git 会显示 `both modified`、`deleted by us` 等状态。文本文件可能出现：

    <<<<<<< HEAD
    当前分支中的内容
    =======
    本次合并进来的内容
    >>>>>>> dev/wsc

“当前”和“传入”取决于合并方向：

| 操作 | 当前 / ours / HEAD | 传入 / theirs |
| --- | --- | --- |
| 在 main 合并 `dev/wsc` | main | dev/wsc |
| 在 dev/wsc 合并 `origin/main` | dev/wsc | origin/main |
| 在 dev/wyf 合并 `origin/dev/wyf` | 本地 dev/wyf | 远程个人分支 |

不要把“当前”固定理解为自己的修改，或把“传入”固定理解为正确版本。

### 9.2 编辑并完成合并

1. 打开冲突文件，结合业务逻辑确定最终内容，必要时与另一位作者协商。
2. 删除冲突标记，保留正确代码；有时需要重新组合双方修改。
3. 保存后暂存已解决文件：

```bash
git add path/to/conflicted-file
git diff --name-only --diff-filter=U
git diff --cached
git diff --cached --check
git status
```

冲突文件列表无输出表示没有未解决的索引冲突。仍需检查是否误留标记，并运行相关验证。全部解决后：

```bash
git merge --continue
git status
```

命令可能打开编辑器填写合并说明，保存退出即可。Vim 中按 `Esc`，输入 `:wq` 回车；Nano 中按 `Ctrl+O` 保存、回车确认，再按 `Ctrl+X` 退出。也可用 `git commit -m "merge: 解决本次合并冲突"` 完成合并。

### 9.3 取消尚未完成的合并

暂时无法确认正确结果时：

```bash
git merge --abort
git status
```

这用于仍在冲突处理中的合并，尽量恢复合并前状态。合并前保证工作区干净，可减少恢复的不确定性。合并提交已生成后，abort 不再适用，见第 14 节。

### 9.4 删除、重命名和二进制冲突

- **一方删除、一方修改：** 保留时编辑最终文件并 `git add 文件路径`；删除时 `git rm 文件路径`。
- **双方重命名或目录移动：** 确认最终路径，整理文件，暂存保留路径及旧路径的删除，避免重复文件。
- **二进制文件：** 图片、压缩包通常无法逐行合并，需选择一方版本或重新生成。

明确决定整份文件采用一方内容时，才使用以下二选一命令。

采用当前版本：

```bash
git restore --ours --worktree -- path/to/conflicted-file
```

采用传入版本：

```bash
git restore --theirs --worktree -- path/to/conflicted-file
```

再 `git add path/to/conflicted-file` 标记解决。这会覆盖该文件已有的冲突处理结果，适用于双方都有文件版本的情况；删除类冲突按上面的保留 / 删除方式处理。

### 9.5 文本不冲突也需验证

例如 WSC 改接口字段、WYF 改调用代码，修改处于不同文件，Git 自动合并成功但运行出错。集成验证需检查接口、配置、数据库和调用关系，不能只看是否出现 `CONFLICT`。

## 10. 保存未完成的工作

工作未完成但需同步时，使用带明确名称的 stash：

```bash
cd /home/guest/hxjm-wsc
git stash push -u -m "wsc: 同步 main 前保存视频功能未完成修改"
git status
```

`-u` 包含未跟踪文件，不包含被忽略文件。本地配置、模型和运行数据需自行备份，不建议用 `-a` 把大量模型或依赖一起存入 stash。

同步代码：

```bash
git fetch origin
git merge origin/main
```

完成后先核对列表，恢复自己的记录：

```bash
git stash list
git stash show --stat 'stash@{2}'
git stash apply 'stash@{2}'
git status
```

`stash@{2}` 只是示例，替换为实际编号。**所有 worktree 共享 stash**，其他人新增或删除记录会改变编号；恢复前必须核对说明，必要时用 `git rev-parse 'stash@{2}'` 记录完整对象 ID，再用该 ID apply。不要默认 `stash@{0}` 属于自己，也不要未经核对直接 pop。

确认修改完整恢复后，重新核对并删除自己的记录：

```bash
git stash list
git stash drop 'stash@{2}'
```

drop 编号以最新列表为准，并与其他成员协调，避免并发变化。apply 不会自动删除备份，有冲突时原 stash 仍保留。

stash 恢复冲突也需编辑、`git add` 标记解决，再按进度提交或继续开发。**这不是 merge 操作，不要使用 `git merge --continue` 或 `git merge --abort`。** 想继续保留为未暂存修改，可对已确认文件执行 `git restore --staged -- 文件路径`。恢复完整前保留原 stash。

## 11. 添加、移动和删除工作树

### 11.1 新成员：创建新分支和目录

新增成员 `abc` 示例，由维护者协调，确认目标目录和分支名称未占用：

```bash
cd /data/nfs_storage/hxjm
git fetch origin
git worktree add -b dev/abc /home/guest/hxjm-abc origin/main
git -C /home/guest/hxjm-abc branch --show-current
git worktree list
```

从 `origin/main` 创建时，Git 可能自动将上游设为 `origin/main`，创建后用 `git branch -vv` 检查。如允许上传，用 `git push -u origin dev/abc` 设置个人上游。

### 11.2 本地分支已存在

确认没有其他工作树检出该分支后：

```bash
git worktree add /home/guest/hxjm-abc dev/abc
```

提示已在别处检出时，先查看 worktree list，使用已有目录，不要强制让两个工作树同时检出同一分支。

### 11.3 远程个人分支已存在，本地没有

```bash
git fetch origin
git worktree add --track -b dev/abc /home/guest/hxjm-abc origin/dev/abc
```

`--track` 明确设置上游为 `origin/dev/abc`。

### 11.4 独立任务分支

并行做新任务、避免交付未完成内容时，可新建任务工作树：

```bash
git fetch origin
git worktree add -b feat/wsc-video-status /home/guest/hxjm-wsc-video-status origin/main
```

该目录只做对应任务，交付时合并 `feat/wsc-video-status`。创建分支不会自动携带原目录的未提交修改，应先明确从哪个提交开始。

### 11.5 移动工作树

停用对应编辑器、终端任务和服务，在主目录执行：

```bash
git worktree move /home/guest/hxjm-abc /home/guest/hxjm-abc-new
git worktree list
```

不要直接用文件管理器或 mv 搬动。主工作树不能按此方式移动，需要调整主目录时由维护者另行迁移。

### 11.6 删除完成的工作树

删除会移除工作目录。先确认修改已交付，依赖、配置、模型、运行数据已按需备份：

```bash
git -C /home/guest/hxjm-abc status --short
git -C /home/guest/hxjm-abc status --short --ignored
git -C /data/nfs_storage/hxjm merge-base --is-ancestor dev/abc main
```

最后一条退出码 `0` 表示该分支全部提交已包含在本地 main，`1` 表示未全部包含。这不证明 main 已推送，仍需确认发布结果。

确认可移除后，在主目录执行：

```bash
git worktree remove /home/guest/hxjm-abc
git worktree list
```

有未提交或未跟踪文件时通常会拒绝，忽略文件也应提前检查和备份。不要用 force 跳过检查。

移除目录不会自动删除分支。分支已交付且不再需要时：

```bash
git branch -d dev/abc
```

拒绝时检查上游和合并状态，不要直接改用 `-D`。远程删除是独立操作，确认团队不再需要后才执行：

```bash
git push origin --delete dev/abc
```

### 11.7 手工删除或失联的目录

正常删除用 worktree remove。确认目录确实被误删、不是暂时卸载或失联时，才清理残留记录：

```bash
git worktree prune --dry-run --verbose
git worktree prune --verbose
```

默认有过期时间，刚删除的记录不一定立即清理。不要为暂时失联的目录强行缩短期限。挂载盘工作树可由维护者 `git worktree lock /path/to/worktree` 防止记录被清理，恢复后 unlock。这个 lock 保护管理记录，不是阻止他人编辑代码的协作锁。

## 12. 完整协作示例

假设初始问题已处理、工作区干净，WSC 和 WYF 各交付一个完整任务。个人远程分支有更新时，先按第 6 节同步它。

### 第一步：WSC 同步、开发、提交

```bash
cd /home/guest/hxjm-wsc
git status
git fetch origin
git merge origin/main

# 在自己的目录修改代码并运行相应验证
git add path/to/wsc-file
git diff --cached
git commit -m "feat: 完成 WSC 本次任务"
git rev-parse --short HEAD
```

需远程备份时，再 `git push -u origin dev/wsc`。

### 第二步：WYF 同步、开发、提交

```bash
cd /home/guest/hxjm-wyf
git status
git fetch origin
git merge origin/main

# 在自己的目录修改代码并运行相应验证
git add path/to/wyf-file
git diff --cached
git commit -m "fix: 完成 WYF 本次修复"
git rev-parse --short HEAD
```

需远程备份时，再 `git push -u origin dev/wyf`。两人交付提交 ID、验证结果，并冻结本次交付内容。

### 第三步：集成人员在 main 依次合并

```bash
cd /data/nfs_storage/hxjm
git status
git fetch origin
git merge --ff-only origin/main
git log --oneline main..dev/wsc
git diff --stat main...dev/wsc
git merge --no-ff dev/wsc -m "merge: 集成 WSC 本次任务"
```

处理冲突、验证 WSC 合并结果，再继续：

```bash
git log --oneline main..dev/wyf
git diff --stat main...dev/wyf
git merge --no-ff dev/wyf -m "merge: 集成 WYF 本次任务"
```

处理冲突、完成组合验证，然后发布：

```bash
git status
git log --oneline origin/main..main
git push origin main
```

### 第四步：两人同步发布的 main

WSC 执行：

```bash
cd /home/guest/hxjm-wsc
git status
git fetch origin
git merge origin/main
```

WYF 执行：

```bash
cd /home/guest/hxjm-wyf
git status
git fetch origin
git merge origin/main
```

## 13. 常见问题

### 13.1 个人目录为什么不能切换到 main？

main 已在主目录检出。出现 `already checked out` / `already used by worktree` 时，进入对应工作树操作，不要绕过检查。

### 13.2 提交后为什么 main 看不到文件变化？

提交只更新当前个人分支，main 需要合并。共享提交对象不代表共享当前检出的文件内容。

### 13.3 pull 后为什么仍没其他人的代码？

无参数 pull 使用当前上游，可能是 `origin/dev/wyf`。检查 `git branch -vv`，同步 main 用 fetch 后 merge origin/main。

### 13.4 为什么提示本地修改会被覆盖？

先 status、diff 检查，提交完成内容或 stash。不要为完成拉取直接执行 `git reset --hard`。

### 13.5 Already up to date，但文件不同？

merge 按祖先关系判断，不会强行让目录内容相同。个人分支可能有额外修改，或历史中存在 revert。还需检查未提交修改、忽略文件、fetch 是否完成和分支是否正确。用 `git diff main dev/wsc` 查看最终文件差异，再分析历史，不要重复 merge 试图覆盖文件。

### 13.6 可以同时 fetch 吗？

远程跟踪引用共享，一处 fetch 后其他目录也能看到。并发 fetch、修改共享配置或管理分支可能遇到锁和状态变化，尽量错开；同一目录内的提交、合并、拉取应串行。

### 13.7 index.lock / 引用锁错误怎么处理？

检查是否有 Git、编辑器后台 Git 或合并编辑器运行，等待正常操作结束。持续出现时，由维护者确认具体锁和对应进程已退出，再处理遗留锁。不要直接删除所有工作树中的锁，以免影响正在进行的操作。

### 13.8 个人目录可以直接推送 main 吗？

技术上 `git push origin main` 推送本地 main，不受所在目录限制。但团队约定只允许集成人员在主目录验证后推送；在个人目录运行该命令，不意味着自己的提交自动进入 main。

### 13.9 如何检查某次交付已集成？

用交付记录的实际提交 ID：

```bash
git fetch origin
git merge-base --is-ancestor 提交ID origin/main
```

退出码 `0` 表示已包含，`1` 表示未包含。cherry-pick 或 squash 会产生不同 ID，不能仅靠祖先检查判断内容已交付，应检查说明和实际差异。本文默认普通 merge，通常可按祖先关系确认。

## 14. 撤销和恢复

### 14.1 取消暂存，保留修改

```bash
git restore --staged -- path/to/file
```

只移出暂存区，文件修改仍保留。

### 14.2 放弃某文件未暂存修改

确认不需要保留并按需备份后：

```bash
git restore --worktree -- path/to/file
```

恢复为暂存区版本，丢弃未暂存修改。未提交且未 stash 内容通常无法用 Git 恢复，不要作为同步前常规操作。

### 14.3 撤销普通提交

已共享或已推送的提交，优先生成新的撤销提交：

```bash
git revert 提交ID
```

冲突解决并暂存后 `git revert --continue`；取消正在进行的 revert 用 `git revert --abort`。验证后按分支职责交付或推送。

### 14.4 撤销 main 上某次合并

集成人员先检查父提交，确认第一父提交是合并前的 main：

```bash
git show --no-patch --pretty=raw 合并提交ID
```

确认保留该主线后：

```bash
git revert -m 1 合并提交ID
```

处理冲突、验证后推送 main。`-m 1` 表示相对第一父提交撤销合并引入的变化，不是填写提交说明。

revert 不删除原分支历史，以后直接再次 merge 同一批提交，可能不会带回被撤销代码。需要恢复时，由维护者决定撤销那次 revert 或提交新修复，并评估期间其他变化。

### 14.5 误在 main 开发或提交

先停下新的 main 操作并与集成人员协调。未提交修改可保存到带名称 stash，再在正确工作树恢复。已提交则记录 ID，需要保留的内容可在正确分支 `git cherry-pick 提交ID` 接收，再决定 main 如何清理。已共享或已推送 main 用 revert 撤销，避免改写历史。

不要未经检查直接 reset hard。调整仅本地、未共享提交时，由维护者确认备份和影响范围后操作。

### 14.6 查找误操作前的提交

```bash
git reflog
git reflog show dev/wsc
```

找到要保留的提交后，先建立恢复分支，不立即移动现有分支：

```bash
git branch rescue/wsc-20261010 提交ID
```

名称需不重复。reflog 有保留期限，不能保证找回未提交文件，不能替代提交或备份。

## 15. VS Code 使用方式

1. WSC 打开 `hxjm-wsc`，WYF 打开 `hxjm-wyf`，集成人员打开 `hxjm`，每个工作树使用独立窗口。
2. 查看左下角分支，确认窗口与分支相符。
3. 打开 **Source Control / 源代码管理**（`Ctrl+Shift+G`），检查 diff，选择文件暂存并提交。
4. 首次同步、修复上游、合并 main 时，优先在对应窗口终端用本文明确指定分支的命令。
5. Merge Editor 中按第 9 节确认 Current / Incoming 的实际分支，检查最终内容，保存并暂存后完成合并。

**Sync Changes / 同步更改** 通常根据上游拉取、推送，也受编辑器配置影响。当前 dev/wsc 的上游是 origin/main，修复前不要依赖该按钮。即使上游正确，它也不代替“同步 main”；仅 main 上传时不使用个人分支的同步推送功能。

未显示仓库时，可命令面板执行 **Git: Open Repository** 选择自己的 worktree，或 **Developer: Reload Window**。

## 16. 运行环境与忽略文件

### 16.1 worktree 不自动复制本地环境

新工作树会检出跟踪文件，不会复制其他目录的 `node_modules`、构建产物、未跟踪 / 忽略的环境配置、模型权重和日志。每个目录需按项目及模块文档准备依赖和本地配置。

同时运行多个工作树服务时，检查端口、容器名、数据库、运行数据目录和 GPU。相同默认端口或 Docker Compose 项目名可能冲突，应按实际配置设置各自资源，或约定一个工作树运行公共服务。Git 隔离代码目录，不隔离进程和数据库。

脚本可能包含绝对路径，启动前检查是否指向自己的目录。不要为本机路径差异覆盖他人的配置并提交。

### 16.2 忽略规则

根及子目录 `.gitignore` 共同生效。源代码、依赖清单、示例配置、共享资源纳入版本管理；依赖目录、构建产物、日志、录像、权重、运行数据、私密配置、本机编辑器设置按规则保留本地。

检查忽略原因：

```bash
git check-ignore -v path/to/file
```

已跟踪文件不会因加入 .gitignore 就停止跟踪。需移出版本管理时先与团队确认，再使用 `git rm --cached` 并提交规则变化。不要随意 `git add -f` 上传私密配置或大型文件。

### 16.3 现有目录管理方式

项目由根仓库统一管理。初始化前，`lanhu`、`SmartMonitor-wangzj`、`mtx` 各有独立 Git 元数据，原元数据备份于 `.git-root/nested-repositories/<目录名>/`，备份不上传。三个子目录由根仓库直接跟踪，日常按当前 worktree 根仓库提交，不在子目录重新 git init。

本机 `.vscode/settings.json` 含本地环境设置，按现有忽略规则保留本地，新工作树是否需配置由实际编辑器设置决定。

## 17. 常用命令速查

修改、合并、恢复类命令执行前确认工作区和分支；origin 分支在 fetch 后使用。

| 目的 | 命令 |
| --- | --- |
| 查看工作树 | `git worktree list` |
| 当前分支 | `git branch --show-current` |
| 修改状态 | `git status` |
| 分支及上游 | `git branch -vv` |
| 已知远程分支 | `git branch -r` |
| 获取远程更新 | `git fetch origin` |
| 个人分支同步 main | 在个人目录 `git merge origin/main` |
| 同步 WSC 远程个人提交 | 在 WSC 目录 `git merge origin/dev/wsc` |
| main 快进更新 | 在主目录 `git merge --ff-only origin/main` |
| 未暂存差异 | `git diff` |
| 暂存差异 | `git diff --cached` |
| 按片段暂存 | `git add -p` |
| 暂存文件 | `git add path/to/file` |
| 取消暂存但保留修改 | `git restore --staged -- path/to/file` |
| 提交 | `git commit -m "说明本次修改"` |
| 首次推送个人分支（如允许） | `git push -u origin dev/wsc` |
| 后续推送个人分支（如允许） | `git push origin dev/wsc` |
| main 合并 WSC | 在主目录 `git merge --no-ff dev/wsc` |
| main 推送 | 在主目录 `git push origin main` |
| 未进入 main 的提交 | `git log --oneline main..dev/wsc` |
| 个人变更范围 | `git diff --stat main...dev/wsc` |
| 分支最终内容差异 | `git diff main dev/wsc` |
| 最近提交图 | `git log --oneline --graph --decorate --max-count=30 --all` |
| 未解决冲突 | `git diff --name-only --diff-filter=U` |
| 完成冲突合并 | `git merge --continue` |
| 取消未完成合并 | `git merge --abort` |
| 保存未完成工作 | `git stash push -u -m "姓名: 用途"` |
| 查看共享 stash | `git stash list` |
| 恢复确认属于自己的 stash | `git stash apply 'stash@{实际编号}'` |
| 检查提交进入远程 main | `git merge-base --is-ancestor 提交ID origin/main` |
| 移除完成的工作树 | `git worktree remove /path/to/worktree` |

## 18. 交付和集成检查清单

开发人员交付前：

- [ ] 目录和分支属于自己。
- [ ] 需要交付的文件已提交，未混入未完成任务。
- [ ] 已获取远程更新、同步需要的个人远程分支和 origin/main。
- [ ] 冲突已解决，相关模块已验证。
- [ ] 未提交私密配置、权重、日志和临时产物。
- [ ] 已说明分支、提交 ID、变更和实际验证结果。
- [ ] 跨电脑开发或团队要求远程备份时，已推送个人分支。

集成人员发布前：

- [ ] 当前在主目录 main，无他人同时操作主工作目录。
- [ ] main 工作区干净，已检查并整合远程更新。
- [ ] 已审查待交付分支全部提交和变更范围。
- [ ] 已逐个合并、解决冲突，无未解决文件或遗漏标记。
- [ ] 已验证组合行为。
- [ ] main 推送成功，远程状态已确认。
- [ ] 已通知开发者同步发布的 main。
