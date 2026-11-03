# HXJM 协同开发流程

本文约定：WSC 和 WYF 分别在自己的工作目录、个人开发分支中开发，提交并推送到各自的远程分支；集成人员在 `main` 中合并已推送的开发成果，验证后推送远程 `main`；每位成员在下一轮开发前同步 `main`，解决冲突、推送个人分支后再开始开发。

## 1. 工作目录与分支

| 角色 | 工作目录 | 本地分支 | 对应远程分支 |
| --- | --- | --- | --- |
| WSC | `/home/guest/hxjm-wsc` | `dev/wsc` | `origin/dev/wsc` |
| WYF | `/home/guest/hxjm-wyf` | `dev/wyf` | `origin/dev/wyf` |
| 集成人员 | `/home/guest/hxjm` | `main` | `origin/main` |

以上目录是当前服务器的 Git worktree。各成员在自己的目录操作；需要集成时，集成人员进入 `main` 所在目录。其他电脑使用各自实际的仓库目录。

远程名称统一使用 `origin`。`origin/main`、`origin/dev/wsc` 等是本地保存的远程分支记录，需要先执行 `git fetch origin` 才能获取最新状态。

## 2. 一轮协作的顺序

```text
成员进入自己的工作目录
          ↓
获取远程更新，先同步自己的远程开发分支
          ↓
把 origin/main 合并进自己的开发分支
          ↓
解决冲突、验证，并推送自己的远程开发分支
          ↓
开始本轮开发，完成后提交、推送自己的远程开发分支
          ↓
集成人员获取远程更新，在 main 合并成员的远程开发分支
          ↓
解决冲突、验证，并推送 origin/main
          ↓
成员下一轮开发前再次同步 main，重复上述流程
```

团队统一通过 **merge** 同步长期开发分支，保留已有提交历史。普通 `git pull` 同步的是当前分支的上游，不能代替把 `origin/main` 合并进个人分支。

## 3. 首次配置

当前仓库已启用 `extensions.worktreeConfig`，各成员可在自己的目录中分别设置拉取策略。

WSC 执行：

```bash
cd /home/guest/hxjm-wsc
git config --worktree pull.rebase false
```

WYF 执行：

```bash
cd /home/guest/hxjm-wyf
git config --worktree pull.rebase false
```

这会让当前工作区的 `git pull` 默认使用 merge。下面的日常流程使用明确的 `fetch` 和 `merge` 命令，不依赖隐含的拉取策略。

检查个人分支的上游：

```bash
git branch -vv
```

`dev/wsc` 应跟踪 `origin/dev/wsc`，`dev/wyf` 应跟踪 `origin/dev/wyf`。远程个人分支已经存在时，可以在对应目录修正：

```bash
# WSC 在自己的目录执行
git branch --set-upstream-to=origin/dev/wsc dev/wsc

# WYF 在自己的目录执行
git branch --set-upstream-to=origin/dev/wyf dev/wyf
```

如果远程个人分支尚不存在，确认本地提交可以上传后，在自己的目录执行 `git push -u origin dev/wsc` 或 `git push -u origin dev/wyf`，创建远程分支并设置上游。远程分支创建前，跳过日常流程中合并该远程个人分支的步骤。

## 4. 成员开发前：同步并推送

### 4.1 确认目录、分支和工作区

在自己的目录执行：

```bash
git branch --show-current
git status
```

确认当前分支是自己的开发分支，且工作区干净。如果有未提交修改，先提交已完成的内容，或保存未完成的内容，再进行合并。

以下命令按顺序执行。任何一步报错或出现冲突，都先处理完成，再执行下一步。

### 4.2 WSC 同步

```bash
cd /home/guest/hxjm-wsc

# 获取最新的远程分支记录
git fetch origin

# 先同步自己的远程开发分支
git merge origin/dev/wsc

# 再把团队主分支合并进自己的开发分支
git merge origin/main

# 解决冲突并完成相关验证后，推送同步结果
git push origin dev/wsc
```

### 4.3 WYF 同步

```bash
cd /home/guest/hxjm-wyf

git fetch origin
git merge origin/dev/wyf
git merge origin/main

# 解决冲突并完成相关验证后，推送同步结果
git push origin dev/wyf
```

先同步自己的远程分支，可以整合其他电脑已经推送的提交；再同步 `main`，可以获得其他成员已集成的代码。推送成功后开始本轮开发。

## 5. 成员开发完成：提交并推送

在自己的开发目录修改代码，完成相关测试、构建或运行检查后，检查并提交本次修改：

```bash
git status
git diff

# 将下面的示例路径替换为本次需要提交的实际文件
git add path/to/file1 path/to/file2
git diff --cached
git diff --cached --check
git commit -m "feat: 说明本次完成的功能"
```

WSC 推送：

```bash
git push origin dev/wsc
```

WYF 推送：

```bash
git push origin dev/wyf
```

推送成功后，向集成人员说明本次交付的分支、提交 ID、变更内容和验证结果。可用以下命令获取提交 ID：

```bash
git rev-parse --short HEAD
```

合并个人分支会包含该分支所有尚未进入 `main` 的提交。交付分支中的内容应当都已完成并可集成；审查期间如需追加提交，与集成人员确认本次交付范围。

## 6. 集成人员：在 main 汇总并发布

### 6.1 更新 main

仅由集成人员在主工作目录操作，同一时段由一人完成集成。

```bash
cd /home/guest/hxjm
git branch --show-current
git status
```

确认当前分支为 `main`、工作区干净后执行：

```bash
git fetch origin
git merge --ff-only origin/main
```

`--ff-only` 在能够快进时更新 `main`。如果提示无法快进，先检查本地和远程的独有提交，再决定如何整合，参见第 8 节。

### 6.2 审查并逐个合并成员分支

使用成员已经推送的远程开发分支作为交付来源，即使在同一台服务器上，也统一合并 `origin/dev/wsc`、`origin/dev/wyf`。

先审查并合并 WSC：

```bash
git log --oneline main..origin/dev/wsc
git diff --stat main...origin/dev/wsc
git diff main...origin/dev/wsc
git merge --no-ff origin/dev/wsc -m "merge: 合并 WSC 本次开发"
```

解决冲突、完成对应验证后，再审查并合并 WYF：

```bash
git log --oneline main..origin/dev/wyf
git diff --stat main...origin/dev/wyf
git diff main...origin/dev/wyf
git merge --no-ff origin/dev/wyf -m "merge: 合并 WYF 本次开发"
```

根据任务依赖调整顺序，也可以每次只合并一个成员分支。`--no-ff` 在有待合入提交时保留独立的合并提交，便于追踪每次集成。

第二个分支可能与刚合入的第一个分支冲突。即使 Git 自动合并成功，也要验证接口、调用关系和组合行为。

### 6.3 验证并推送 main

完成集成测试、构建或运行检查后：

```bash
git status
git diff --check origin/main main
git log --oneline origin/main..main
git push origin main
```

推送成功后，通知成员 `main` 已更新。成员在下一轮开发前按照第 4 节同步、解决冲突并推送自己的分支，再开始开发。

## 7. 合并冲突处理

以下步骤适用于个人分支同步远程分支、个人分支合并 `main`，以及 `main` 合并成员分支。

### 7.1 查看冲突

```bash
git status
git diff --name-only --diff-filter=U
```

文本冲突可能显示以下标记：

```text
    <<<<<<< HEAD
    当前分支的内容
    =======
    本次合并进来的内容
    >>>>>>> origin/main
```

根据实际需求编辑最终内容，并删除冲突标记。不要仅按“当前”或“传入”的名称选择内容，要先确认合并方向：

| 合并操作 | 当前内容 / HEAD | 传入内容 |
| --- | --- | --- |
| 在 `dev/wyf` 合并 `origin/main` | WYF 开发分支 | 团队主分支 |
| 在 `main` 合并 `origin/dev/wyf` | 主分支 | WYF 已推送的开发分支 |

### 7.2 完成合并

解决每个冲突后，将文件路径替换为实际路径：

```bash
git add path/to/conflicted-file
git diff --name-only --diff-filter=U
git diff --cached --check
git diff --cached
```

确认没有未解决冲突，最终内容正确后，完成合并：

```bash
git merge --continue
git status
```

如果打开提交说明编辑器，确认说明后保存并退出。完成相关验证，再继续原流程中的下一次合并或推送。

如果决定取消当前尚未完成的合并：

```bash
git merge --abort
```

## 8. 常见问题

### 8.1 pull 提示需要指定分叉处理策略

```text
fatal: Need to specify how to reconcile divergent branches.
```

这表示本地与远程各有独有提交，Git 没有确定采用 merge 还是 rebase。即使两边修改的文件内容相同，只要提交历史不同，也可能分叉。

按照本文流程，获取远程更新后显式合并自己的远程分支即可。WYF 示例：

```bash
git fetch origin
git merge origin/dev/wyf
```

也可以在工作区干净时单次使用 `git pull --no-rebase origin dev/wyf`。随后仍需要执行 `git merge origin/main` 才能同步主分支。

### 8.2 推送被拒绝：non-fast-forward

先获取并合并对应远程分支。WYF 示例：

```bash
git fetch origin
git merge origin/dev/wyf
```

处理冲突、验证后，再执行 `git push origin dev/wyf`。WSC 替换为 `dev/wsc`。

如果是 `main` 推送被拒绝，由集成人员执行：

```bash
git fetch origin
git log --oneline --left-right main...origin/main
git merge origin/main
```

确认远程提交合理，解决冲突并重新验证后，再推送 `main`。通过合并整合双方提交，不用强制推送覆盖远程历史。

### 8.3 main 更新时提示无法快进

在主目录检查：

```bash
git log --oneline --left-right main...origin/main
```

`<` 表示本地独有提交，`>` 表示远程独有提交。仅有本地独有提交且确认为待发布的集成结果时，可继续审查和发布；双方都有独有提交时，确认来源后执行 `git merge origin/main`，解决冲突并重新验证。

### 8.4 拉取成功，但没有其他成员的代码

个人分支的 `git pull` 通常只同步自己的远程分支。其他成员的成果需要先由集成人员合并并推送到 `main`，再由成员执行：

```bash
git fetch origin
git merge origin/main
```

### 8.5 提示本地修改会被合并覆盖

先检查并提交已完成的修改。尚未完成时，可在自己的目录保存：

```bash
git stash push -u -m "wyf: 同步 main 前保存未完成修改"
```

完成同步后，用 `git stash list` 找到自己的记录，核对内容，再恢复：

```bash
git stash list
git stash show --stat 'stash@{实际编号}'
git stash apply 'stash@{实际编号}'
```

`实际编号` 需要替换为列表中的编号。同仓库的 worktree 共享 stash，恢复前必须核对记录归属。恢复产生的冲突要编辑并暂存解决；stash 恢复不是 merge 操作，不使用 `git merge --continue`。确认修改完整恢复后，再删除对应 stash 记录。

## 9. 日常操作速查

所有合并前先确认工作区干净，所有 `origin/*` 合并前先 fetch。遇到冲突时暂停后续命令，处理完成再继续。

| 阶段 | WSC | WYF |
| --- | --- | --- |
| 进入目录 | `cd /home/guest/hxjm-wsc` | `cd /home/guest/hxjm-wyf` |
| 获取更新 | `git fetch origin` | `git fetch origin` |
| 同步个人远程分支 | `git merge origin/dev/wsc` | `git merge origin/dev/wyf` |
| 同步主分支 | `git merge origin/main` | `git merge origin/main` |
| 推送同步结果，开始开发 | `git push origin dev/wsc` | `git push origin dev/wyf` |
| 开发后暂存并提交 | `git add <实际文件>`，`git commit -m "提交说明"` | `git add <实际文件>`，`git commit -m "提交说明"` |
| 推送开发成果，交付集成 | `git push origin dev/wsc` | `git push origin dev/wyf` |

集成人员在 `/home/guest/hxjm` 更新 `main`，审查并逐个合并 `origin/dev/wsc`、`origin/dev/wyf`，验证后执行 `git push origin main`。成员下轮开发前再次同步，持续循环。
