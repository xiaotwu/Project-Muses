# 多轮工作整理：2026-10-21

## 2026-10-26 播放次数修复与新增排序验收，暂不发布

[XW-128](https://linear.app/xiaotwu/issue/XW-128)修复导入Songs投影丢失已保存的播放次数／年份／流派。[PR #22](https://github.com/xiaotwu/Muses-Polyhymnia/pull/22)经独立审查、定向红绿回归和完整CI后合并为`0104420b46ffd2359acab1e1435ac35b117def22`，产品输入与已验证源码`a8e95c5`同值。22项相关测试通过；完整CI报告1,111项／150套件（9项显式条件跳过），严格线程15项、独立磁盘恢复1项、发布配置50项及元数据／依赖／签名预览上传均成功。

新隔离Release `20261026.1`仅在后台运行，真实确认两首歌曲Plays从错误0恢复为原存储1，并新增Plays与Date Added菜单升序验收，原始编号保留。已通过的验收格不重复执行。535曲目全字段、1064导入成员、40事件及534队列语义／顺序保留；21业务表精确同值，实际状态／ORM及JSON序列化差异单列。分页仅为停止态准备；原生设置开关、完整表列头／降序和多书签草稿输入仍未取得有效后台证明。详见[本轮完整记录](../Muses-Polyhymnia/docs/engineering/imported-song-metadata-2026-10-26.md)。

三个候选正常退出，会话结束。应用完整ZIP各623项、最终资料126项及877项冻结源码经独立核对；14个自有运行／构建／偏好路径清理，完整失败与最终证据保留，正常安装／资料／偏好及共享构建五根无变化。Linear已同步7个事项及两份Muses项目文档并回读保留原历史、关系与状态。新窄缺陷XW-128 Done；当前114项，91 Done，原23项仍开放（17 In Review、6 In Progress）。XW-74、Premium、Erato暂停保持。

子仓库工程记录已提交并推送至`0e3a6ce8c2293bbb4e80d49434efd80d92ddd8e2`，本仓库随后更新Polyhymnia引用。五份子仓库工程文档122个本地链接及本轮家族工程记录链接通过校验，产品输入仍与已验证源码一致；已经通过的产品验收不重复。Erato／Euterpe引用不变，未修改公开站点、更新源或发行资产；本轮路径不触发Pages，**暂不发布**。

## 2026-10-26 后台验收接续，暂不发布

精确复用已验证的隔离Release `20261025.3`：623项完整应用清单、签名及当前产品源码一致。新增EQ Reset→Flat→原预设、零曲目MiniPlayer／桌面歌词空态、公共歌单详情→Library→YouTube来源隔离与恢复，以及两条发行详情历史分叉／Forward回B的实际证据。Diagnostics重复打开保持单窗口并正常关闭；配置展开无可验证变化，Preview／Cancel仍待验。独立源码与证据审查未发现新产品缺陷，本轮没有源码补丁或重新构建。详见[10月26日后台验收](../Muses-Polyhymnia/docs/engineering/background-acceptance-2026-10-26.md)。

初始／最终停止态和四份中间实时备份的完整27表、schema及PRAGMA严格同值。EQ参数和两个功能开关恢复；候选完整偏好5→15键及JSON键序差异单列，未声称精确恢复。候选正常退出；完整121项资料归档验证后，仅清理本轮隔离应用／资料／偏好／注册，旧归档和所有证据保留，五保护根不变。

Linear的11个相关事项及两份Muses项目文档已更新回读，历史、归属、原状态和父子关系保留。项目113项：90 Done，原23项开放（17 In Review、6 In Progress）。未把后台工具限制当产品缺陷或通过；删除菜单、配置预览、实体输入、其他业务／来源／账号／平台／VoiceOver条件仍逐项开放。XW-74、Premium和Erato暂停保持。

子仓库工程记录先提交并推送至`28f4288c7a648e897f259a02cf7e09b9093f8961`，家族仓库随后更新引用。117个子仓库文档本地链接、家族站点链接、政策／图标一致性及六项模拟发布同步检查通过。模拟输出不是实际发布；本次只改工程记录和Polyhymnia引用，不触发Pages。Erato／Euterpe引用不变，**暂不发布**，未改更新源或发行资产。

## 2026-10-25 后台接续：两处新修复与限定验收

[PR #21](https://github.com/xiaotwu/Muses-Polyhymnia/pull/21)已合并为`fd8f7c5`，与已验源码`128f14f`整树一致：XW-126修复空资料库Home的过期Retry引导，XW-127修复EQ保存失败后名称不可见但草稿仍被保存的问题。两子项Done；Muses项目回读113项、90 Done，原23项仍开放（17 In Review、6 In Progress）。11个受影响父项及两份项目文档已更新并读回，历史、状态与父子关系保留。

新隔离Release `20261025.3`实际验证中英文Home／Search、EQ空名称禁用／Cancel保留、真实ENOSPC失败同表单显示名称及错误／恢复空间后直接重试／冷恢复。失败前后27表同值，成功恰新增1个预设且原两项保留。旧`.2`另补齐目录语言变化后真实续页／Home返回、Diagnostics主题切换／版本刷新与Bypass On冷恢复。42项定向及独立复核通过；[完整CI](https://github.com/xiaotwu/Muses-Polyhymnia/actions/runs/40270064841)报告1,110项／150套件（9项条件跳过），15项严格线程、磁盘恢复、50项发布配置、元数据／依赖／签名打包上传成功。详见[本轮证据](../Muses-Polyhymnia/docs/engineering/background-acceptance-2026-10-25.md)。

四个自有进程正常退出；完整应用／资料归档验证后，专属测试卷卸载，隔离应用／资料／偏好／注册及临时构建清理，独立复核通过。正式应用、正常资料／偏好、共享构建五根同值。实体Escape被后台路由拒绝，删除菜单／配置预览重复展开／闭窗Settings及其他业务、账号、平台、VoiceOver矩阵仍待验。XW-74、Premium和Erato暂停保持，Erato／Euterpe引用不变。

子仓库main修复与工程记录先推送至`0ad3749`，本仓库随后更新引用；本轮站点链接、政策／图标一致性和六项模拟同步检查通过。本提交仅修改工程记录和子模块引用，不触发Pages发布。**暂不发布**，公开应用保持0.6.2／20261023.4，未改更新源或发布资产。

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
