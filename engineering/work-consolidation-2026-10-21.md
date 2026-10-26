# 多轮工作整理：2026-10-21

## 2026-10-25 接续：四项修复整合与剩余范围

逐项回读 Muses 原有23个开放事项，确认并修复四个独立缺陷：XW-122 EQ保存／删除失败保留，XW-123目录详情语言／地区重载，XW-124无主窗口设置目的地交接，XW-125音频信息显示自定义EQ名称。[PR #20](https://github.com/xiaotwu/Muses-Polyhymnia/pull/20)已合并为`912b2d6`，提交树与已验证源码`878f9bf`同值；四子项均Done。项目回读111项：88 Done，原23项开放（17 In Review、6 In Progress）；原父子关系、状态及历史证据保留。

[完整CI 40264965125](https://github.com/xiaotwu/Muses-Polyhymnia/actions/runs/40264965125)通过1,107项／150套件（9项显式条件跳过）、15项严格线程、独立磁盘恢复、50项发布检查，以及App Intents元数据、固定音频依赖和签名预览打包上传。四项修复独立交叉审查无阻塞。隔离Release后台实际验证EQ保存即时刷新／冷恢复、新名称即时显示，以及同一真实专辑英文→简体中文加载／内容→System英文恢复；原生删除菜单未打开、闭窗设置会激活等条件继续未验。完整逐项范围见[开放项复核清单](../Muses-Polyhymnia/docs/engineering/remaining-open-issues-2026-10-25.md)。

本轮两个新候选各470个文件／符号链接与归档逐项同值，正常退出后清理自有应用、资料／偏好、注册及临时构建。正式应用、正常资料／偏好和共享构建五个保护根同值；旧候选及旧证据保留。后台操作限制、XW-74测量跳过、Premium／Erato暂停保持。剩余事项包含可继续分项验证的视觉／错误／持久化分支，以及实际macOS26、VoiceOver、设备、账号和实体焦点条件，不能统称已完成或全部外部阻塞。本轮没有新应用或网站发布，公开版仍为0.6.2／20261023.4。

另复用保留的`20261023.4`隔离候选补齐[Songs长标题格](../Muses-Polyhymnia/docs/engineering/post-release-acceptance-2026-10-23.md#songs-long-title-follow-up--october-25-2026)：840×804、Dark／Large选中值、真实长标题省略和控件边界均有原生证据；不播放、不改歌单。严格focus-only审计零违规，535曲目、534队列曲目／occurrence顺序及40事件保留；15偏好恢复、正常退出、注册／会话撤回、候选原件与五保护根同值。XW-9／19仍保留其他验收条件，下面10月24日的“Songs长标题待验”由此接续。

子仓库main的代码整合及证据记录已依次推送至`354d80e`，家族仓库随后跟进该引用。站点本地链接、生成政策／图标一致性和六项模拟发布同步检查通过；模拟测试的发布文字不代表执行任何实际发布。Erato、Euterpe引用保持不变。

## 2026-10-24 接续：发布后限定验收

已恢复[最小宽度焦点卡与连续桌面歌词验收](../Muses-Polyhymnia/docs/engineering/post-release-acceptance-2026-10-23.md)。Dark／Large、840×804 的 Songs／导入 Liked 卡片选择、列表展开收起、长资料省略与 PlayerBar 边界取得实际画面，focus-only 数据审计零违规。真实 LRCLIB 匹配录音从暂停 0:30 一次播放，自然跨过 32.24／35.39 秒，独立复核两张桌面歌词及主时钟画面。用户明确仅后台操作，浏览条拖动／键盘焦点、Songs 长标题变体及更大矩阵仍待验；不将工具限制记为产品缺陷或验收通过。

隔离候选正常退出，桌面歌词关闭、Prima 暂停 1:11／534 曲目上下文及 15 项偏好恢复；535 曲目身份、原 38 条事件和队列曲目顺序保留，新增 2 条换曲 skipped 事件（不代表完整播放），歌词／播放／队列标识变化精确单列。十个保护根同值，正式安装、正常资料及已发布资产保持。XW-19／9／72／14 保留原状态与父子关系，XW-74／Premium／Erato 暂停保持。本次只更新工程验收记录及子模块引用，没有重建、产品源码修改或新发布。

## 2026-10-23 接续：PR #19 与新 RC

PR #18、#17、#19 已分别审阅合并；XW-107／118／119／120／121 的窄修复 Done。含 XW-121 的新冻结版本源码为 `73f1dbe6e5a93f6cb7fdf147e98f2e8ef037ee12`，0.6.2 / build `20261023.4`，完整 CI 40042082311 通过。全新 Release／音频依赖、1,092 项回归、15 项严格线程检查、50 项发布检查、Developer ID、应用及 DMG 公证、完整归档及离线签名 feed、9/9 固定媒体冷态播放、实际控制／暂停重启和目录返回小节已完成。详细身份、摘要、资料差异和证据边界见[新 RC 回执](../Muses-Polyhymnia/docs/engineering/release-candidate-pr19-2026-10-23.md)。

用户确认本轮 `.4` 连续正常音乐后，已公开 [v0.6.2](https://github.com/xiaotwu/Muses-Polyhymnia/releases/tag/v0.6.2)，tag 精确指向 `73f1dbe`，stable/latest 与三个资产实际匿名下载均核对通过。公开 feed 的签名、归档签名及旧三条全部字段均通过，updates 保持 prerelease。家族 [polyhymnia/v0.6.2](https://github.com/xiaotwu/Project-Muses/releases/tag/polyhymnia%2Fv0.6.2) 已按相同字节及 source-release.json 聚合；不重建、不改变安装限制。官网 `/releases/latest` 实际跳转新版本，macOS14/15 的0.5.11入口返回200；无需修改网站链接或额外部署Pages。已接续[发布后验收](../Muses-Polyhymnia/docs/engineering/post-release-acceptance-2026-10-23.md)，但当前 Mac 锁屏使驱动读取零 AX 元素并拒绝 Settings 操作；两项界面小节没有新增通过，须待唤醒解锁后继续及正常退出隔离候选。XW-74／Premium／Erato 暂停保持。

Linear 全部工作仍仅属于 Muses：107 项，84 Done、23 开放。新回执保留 535 曲目非播放资料、534 队列顺序、旧事件和精确集合 ID 变化说明；15 项候选偏好恢复、十个保护根同值，自有进程与会话结束。家族站点本地链接、政策／图标一致性及六项模拟发布同步测试通过；这六项测试不代表实际发布。

以下保留原 10 月 21 日整理检查点。

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
