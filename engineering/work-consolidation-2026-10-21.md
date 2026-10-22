# 多轮工作整理：2026-10-21

本轮核对家族仓库、三个子模块、macOS 独立 worktree 与五个相关对话。各工作目录未发现未提交源码；`~/Code/Muses`、`~/Code/Muses-Polyhymnia` 指向本仓库的 macOS 子模块，不是另外一份待提交的工程。

## 提交归档

- macOS 已有修改保存在 main 和已推送的 PR 分支；本轮追加 Linear 工作规则与[子仓库整理记录](../Muses-Polyhymnia/docs/engineering/work-consolidation-2026-10-21.md)。
- [PR #16](https://github.com/xiaotwu/Muses-Polyhymnia/pull/16) 保留解析管道修复；[Draft PR #17](https://github.com/xiaotwu/Muses-Polyhymnia/pull/17) 保留三个协作对话整合的 libmpv 播放重构、解析与打包修改和真实验收记录。
- 父仓库子模块引用仅更新至已推送的 macOS main；待验收分支仍在对应 PR 中。Erato、Euterpe 没有待提交修改，引用不变。
- 冷解析超时未定位，0.6.2 继续暂缓、PR #17 保持 Draft、会员音质 deferred、XW-74 继续暂停。本轮未构建、运行候选、替换正式安装或发布版本。

## Linear 归属

创建 [Muses](https://linear.app/xiaotwu/project/muses-5e747ca2af19)，项目 `P-XW-2`，UUID `c2f9c252-e1d1-4210-bbd5-15a5366b9d28`，团队 XW。

103 个 Muses Issue（XW-5 至 XW-107，包含完成项与协调父项）已迁移并完整回读，父子关系一致。只设置 project 字段，保留原状态、描述、历史和关系。现有独立 Linear 文档均属于其他项目，无需迁移。新建项目工作入口文档以汇集上述仓库与待办边界。

父子仓库 AGENTS.md 均已记录唯一项目规则：此后 Muses 家族网站、macOS、iOS、Windows 的 Issue 查询和新建文档/任务都显式指定 Muses 项目。

## 本轮验证

`Scripts/check-site.py` 通过 4 个 HTML 页面与本地链接检查；`Scripts/sync-site-assets.py --check` 通过 iOS 法律页面及 macOS 图标一致性检查；`python3 -m unittest discover -s tests -v` 的 6 项发布同步测试通过。测试使用模拟发布接口，没有实际发布资产。父子仓库 `git diff --check` 通过。本轮是指导/整理文档与 main 子模块引用更新，没有新增原生运行通过结论。
