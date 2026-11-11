# Streaming v2 独立只读审查

本报告检查 v1 六项发现的修正路径，并记录 v2 审查期间发现的三个具体终态问题。
**最终候选的源码、构建绑定和 17 项本地回执已核对，未发现新的具体阻塞。**
一次公开 Opus 的前缀消费、seek 后尾部排空及参考 PCM 比较也已通过。
这关闭了本文列出的具体修正场景，不是通用样本精确 seek、整曲连续播放或产品集成验收。
正起点 M4A seek 和 MKA full 的中间失败继续保留，不被最终通过覆盖。

审查者只阅读源码、固定 FFmpeg 头文件和实现方已有回执，没有联网、编译、运行音频或
生成测试 scratch；唯一新增文件是本文。v1 及 [原六项发现](REVIEW-OF-V1.md) 保持不变，
其绑定提交为 `e42d5fa32e6d3af564991003c978abfef9354829`。

## 版本与证据绑定

下文最新源码位置绑定以下 SHA-256，而非泛指以后修改：

| 文件 | SHA-256 |
| --- | --- |
| [Streaming.cpp](Streaming.cpp) | `b1adba3d2375676d270a144dcd8b3e92463173ea0d671c951e7e7a58b2b19b28` |
| [SourceAdapter.inc](SourceAdapter.inc) | `af3bf8312a072022db2724f21a370c9c738fa69e4dbee1dcc2136d3f90888d13` |
| [run_local.py](run_local.py) | `26d994beeeaaab7114f452d15df48c1f80db8b99c677f3005e510c24d07bc1ef` |
| [run_public.py](run_public.py) | `38e522c9f693410ead07ab1a73412841da1b956eb21f2e98b4eb2ffc858dafd6` |
| [build.py](build.py) | `e431777ab5eda1103e0cbdd9f2220adf8e46e90463932dafa35efe241ee1bf12` |
| [timeline_fixtures.py](timeline_fixtures.py) | `0d53dcb604b0069bed0256af6bd874c6bbbb79dd03d847dd6e516543cad75c07` |

已有回执均位于任务 scratch 的 `audio/macos-streaming/v2/`；后续归档应保留摘要和来源绑定，
无需保留整个编译缓存。审查已读取：

- `local-20261111-002552/results.json`，SHA-256
  `90233fa0b45f457e529cb01f8e6e85d6be1f8d923fac2596890be46232985b0b`。
  对应 `Streaming.cpp` `3c3e4dcc6a036e6569bdac551f63757066014996db76bdc8287408f667505fa8`，
  13 项完成，进程退出码均为零且无外部终止；最高观察 RSS 为 25,706,496 字节。
- `local-20261111-003128/results.json`，SHA-256
  `6a860bc5e26e6793b4b9de03611b4154be12a27727dae0c1c81640440a5c6f13`。
  对应候选 `6211062ab620c0513a966468cfa66938d934486dbf8aa17be439300fb174ddb3`，
  前五项通过，第六项 `positive-mp4-seek` 的完整 PCM 比较失败，不能表述为整组通过。
- 上述第二候选的 `build-20261111-003049/success.json` SHA-256 为
  `03607aa9b9ff4bb393349bd87dc1cc35ed67828e7d30c0fd89ce4131e3a3606d`。
  `deployment.json` SHA-256 为
  `f7fc8b4e3617b4861b441c19a156d0c92cb5de738ecf3420a94d9482f5f20730`，
  记录了全部链接输入及最终产物的部署版本检查；最终程序为 macOS 26.0 minimum / SDK 27.2。
  这不构成在 macOS 26 系统上实际运行的证据；回执正确保留 `runtime_on_macos_26=false`。
- 中间候选 `19355d1d…` 的 `build-20261111-003710/success.json` SHA-256 为
  `c973bd6515b51ec334be481a47ece0abf208cdd3c3acc93de0e6079150884e38`。
  `local-20261111-003720/results.json` SHA-256 为
  `7ca9d0fae65efe7c8e445090a152793edf5bf29399ac69c4ad337cf37384d17e`，
  正起点 M4A seek 单项完整 PCM 比较通过。随后整组
  `local-20261111-003726/results.json` SHA-256 为
  `54ad72c97b08c9af9fcf9af2402d8514a873cc757a1a271ef9b26612c2b2b481`：
  前六项通过，第七项 `positive-mka-full` 比较失败，后续用例没有被此轮执行覆盖。
- 最终 `b1adba3d…` 的 `build-20261111-004247/success.json` SHA-256 为
  `37ade4700255e74564f36e68404bcb54733238003c81584b427d237b1d95c2c9`；
  `stream-local` SHA 为 `223a8575ef622b0b492d04fe27f03dd0a76f85f71754a6d0d9d3472873c55a50`，
  `stream-public` SHA 为 `d967350343f7c7431df46a7acb71acc6e02ebb98bfdca2c9e56b4f050f421b31`。
  `local-20261111-004309/results.json` SHA 为
  `2f0a3767808d07b302d3b45d95171d86587cafd99a7df608d69d2dad59b93b4a`，manifest SHA 为
  `65b4fe8b909c631ee1e545f42771ac972dd609991e2c284d8e3bdc52016d7078`。
  17 项均退出零、无外部终止；11 个完整或 seek PCM 比较均相等，最高观察 RSS 25,477,120 字节。
- `public-20261111-004412/result.json` SHA-256 为
  `80c8188a743ea237bd8b1717af2928ee7d03dd25c56fe1a5450ed9cb3644b5da`。
  该回执绑定上述最终 public binary 和 build success，结果范围见后文。

旧两个构建使用的脚本 SHA 为 `fbe0f6e5134025aa3816f7fe63ead97ea5462f493705caf615953fba34a93ec5`。
最新脚本将编译输入和测试 driver 改为显式哈希清单，独立审查文档由最终证据另行绑定；
这允许补充审查记录而不改变已编译代码的身份，不免除实际输入的哈希核验。

## v1 六项发现的核对

| v1 项 | 最新源码修正 | 已有运行证据与尚未覆盖范围 |
| --- | --- | --- |
| 首输入后期错误可被 next 成功覆盖 | [watchdog](Streaming.cpp#L126)、[join 后错误汇总](Streaming.cpp#L165)、[最终两路检查](Streaming.cpp#L343)；错误、取消、正常 EOF 分开。AVIO 非取消错误另有不可被取消清除的锁存。 | 最终 `late-failure` 确实先有回调消费，随后第二 Range 截断并得到 `input_failed`。其 next 被刻意留空；没有真实并发 next 解析，因此不宣称覆盖解析器并发取消。新锁存交错回归也通过。 |
| codec drain 后缺 SWR drain | [EOF 分支](Streaming.cpp#L261) 要求 codec receive 到 `AVERROR_EOF`，再重复 SWR 空输入直到零，最后才封口。 | `aac-swr-tail` 实际产出 17 个 SWR 排空帧，64,644 帧的生产、消费和完整离线参考 SHA 相同。普通 AAC 或 48→48 kHz Opus 的零 SWR 尾部没有被单独当作该门槛证据。 |
| seek discard/ack 可越过旧 producer 发布 | [consumer](Streaming.cpp#L96) 等待 quiesced；[worker](Streaming.cpp#L255) 在前一发布结束后才公布 quiesced，收到 ack 后再 seek。 | `publish-seek` 受控暂停旧块复制后的发布，确认 ack 没有越过 producer，pending 期间旧内容不再消费；释放后 seek 尾段 PCM 与参考一致。不是只检查 `seek_first_pts`。 |
| 短尾及 EOF/seek 接受语义不一致 | [requestSeek](Streaming.cpp#L160) 与 [drain 封口](Streaming.cpp#L266) 共用控制锁；只接受 Decoding 状态的一次 seek。短尾在全部解码完成时可以 ready。 | 3,985 帧 tiny EOF 及 AAC/Opus 约 50 ms 尾部通过；producer 已 Ended、ring 未空时返回明确拒绝。该原型不支持终态重新 seek，也不声称多次 seek 已实现。新的 sealed-ring 修正见下一节。 |
| duration 被误当成绝对结束 PTS | [origin 与 endPTS](Streaming.cpp#L201)、[seek 目标](Streaming.cpp#L222)、[逐帧相对 PTS](Streaming.cpp#L248)。正 origin 归一化；未知／负 origin 和码率估计不再作硬裁剪终点，AAC 声明 padding 的支持集合被明确限制。 | 最终 M4A/MKA 正起点 full 和 seek 四项全部与零起点 remux 的参考 PCM 相等。只有本文描述的元数据组合通过；未知／歧义组合的拒绝分支经静态检查，尚未逐种生成拒绝 fixture。 |
| 活动取消没有 callback gate | [callback](Streaming.cpp#L139) 入场及逐帧检查取消；[finish](Streaming.cpp#L165) stop/uninit 后 join；最后才销毁 transport。 | 最终活动取消在 stop/join 后 50 ms 无新增消费；满 ring 取消 join 为 54.890 ms。没有观察到悬挂 worker 或取消被当成正常 EOF。尚无专门 drain 中途取消的定点回归；不能把逐帧门限描述为取消标志写入瞬间绝无一次在途消费。 |

读取现有生命周期代码未发现新的 mutex 锁序死锁或已释放对象被 worker/callback 访问的
具体路径：seek 控制锁不进入 callback；句柄在 decoder join 之后销毁；摘要读取在
输出停止和 worker join 之后进行。这是静态核对，不是线程检测器或长时间压力测试结论。

## 本轮新增发现与修正

### A. 一次空读不能证明最终 PCM 已全部消费

在 `3c3e4dcc…` 中，callback 可以先 `pop` 空，producer 随后发布最后 PCM 并置 Ended，
callback 再读到 Ended 就提前设置 `ringDrainNS`。`natural()` 随即停止输出，可能截掉最后
一块；已有摘要相等断言会把丢失检测成失败，因此本发现不声称已出现误报通过。

最终 [consumer](Streaming.cpp#L103) 在 acquire 观察 Ended 后重试 `pop`，仅当 read 等于
producer 预先发布的 `sealedWrite` 才宣布耗尽；[producer](Streaming.cpp#L272) 先封存 write
再 release Ended，且此后不再写 ring；[natural](Streaming.cpp#L291) 再核对 read、seal 和空 ring。
该时序修正已静态确认；最终所有自然 EOF 用例都核对 seal/read/empty。它们没有受控地强制
复现原来的窄交错，因此仍不冒称已经做过定点 EOF 调度测试。

### B. Stop 可覆盖已经发生的非取消 I/O 错误

在 `6211062…` 中，AVIO 已记录 `MT_TRUNCATED` 等真实错误，但 catch 执行前 `finish(6)`
设置取消，catch 会将其归为 Cancelled 而不写 `error`；最终只检查 error 便可能输出通过。

最终 [AVIO read](Streaming.cpp#L83) 在错误返回点锁存首个非 `MT_CANCELLED` 错误；
[catch/退出路径](Streaming.cpp#L280) 及 join 后汇总保留该失败。
[failure-cancel-race](Streaming.cpp#L298) 定点暂停：真实错误已被观察、catch 尚未处理时
请求 bounded stop，然后要求最终为 Failed/input_failed。最终回执记录首个错误 `-12`
（MT_NETWORK_ERROR），请求 stop reason 为 bounded、最终为 input_failed；该定点回归已通过。

### C. 资源停止原因不能被普通用例计为通过

旧终态检查只排除 decoder error，若 watchdog 的 RSS/deadline 先赢 reason CAS，而业务
随后调用 `finish(1/6)`，仍可打印 pass。最终 [expectedReason 检查](Streaming.cpp#L343)
要求断流为 4、取消用例为 1、短段双路观察为 6、自然 EOF 为 5；RSS/deadline 不属于通过集合。
该守卫已静态确认；不声称现有低 RSS 本地样本触发过资源停止交错。

## 时间轴失败与参考的实际含义

`positive-mp4-seek` 的两侧均为 3,211 帧，原型 SHA 为
`74cea6ebe9f21858e969d84fc00e5a6546aa119700bb9baadb03359394d808bd`，
零起点 remux 的离线参考 SHA 为
`6f1d9ee8ccb9af984f6a52ff1ad5537fb44fac17ee7ec872d1c7912d18d3aa70`。
因此失败是样本内容不同，不是仅缺尾帧；同组 full 通过不能抹掉该差异。

最终候选改用整数 origin tick 加相对 seek tick，并在每次 seek 重建 codec/SWR，记录实际
首 packet PTS 和 target 前裁剪帧数。该改动没有从头全曲解码，但“请求 0.12 秒 preroll”
不等于 demuxer 保证只回退恰好 0.12 秒：本地 Opus 的 39.95 秒 seek 实际从 34.994 秒
packet 开始，裁掉 237,576 个转换后帧。M4A seek 比较通过也不能把原差异特指为 AAC PNS、
浮点选点或某一具体内部状态。

`positive-mka-full` 中间失败为原型 65,759 帧、零起点参考 64,644 帧，相差 1,115 帧。
当时 FFmpeg 8 回执的 `presentation_origin_seconds=0.977`，而开发用 FFprobe 9 的 remux
manifest 显示 `start_time=1.000`。后续同版 FFmpeg 8 诊断
`timeline-diagnostic/result.json`（SHA `7e0a41df7077727ba2ac250e262397d749526a63563608d9bfed403ea27786c7`）
确认零起点／正起点 MKA 的 stream、首 packet、首 frame 分别从 -23／977 ticks 开始，
时间基为 1/1000，均声明 `initial_padding=1024` 且无 packet skip。固定
`AVCodecParameters.initial_padding` 契约将其定义为需要丢弃的开头编码填充；因此原先直接
归一化 `start_time` 会把该前导一起移入内容时间轴。

最终规则将 AAC 声明 padding 经 `av_rescale_q` 转到整数容器 tick，再加到 stream start，
本例恢复 origin 0／1 秒，没有硬编码裁掉 1,115 帧。支持范围严格限制为 Matroska、已知
start、未知 duration、无 trailing padding、initial padding 不超过一秒；其余带 AAC padding
的组合返回 `AVERROR_PATCHWELCOME` 并标记 `unsupported_timeline`。已映射流后续遇到非零
packet skip/discard 也明确拒绝，避免重复解释；Opus 不使用该 AAC 映射。
这些拒绝分支已读代码核对，但没有逐个拒绝组合的运行 fixture。

最终 MKA full 为 64,644 帧，full 与 1.30 秒 seek 都和零起点 remux 参考相等。回执同时
披露 padding 换算的量化残差 `0.0002199546s`（约 0.220 ms），没有将粗粒度容器时间基
伪装为精确的源 PCM 时间轴。

[Reference.cpp](Reference.cpp) 使用冻结的完整文件解码路径和同一 FFmpeg；它能检查流式
AVIO/ring 路径丢帧、重复或样本不同，不是另一独立 codec 实现。短 Opus 的 59,731 帧还
独立绑定自生成 PCM 帧数，确实覆盖非整包 pre-skip/discard-padding。旧 40 秒 Opus 在
39.95 秒 seek 后为 2,424 帧，而名义剩余为 2,400 帧；相同参考摘要不能据此推出任意容器
PTS 的样本精确时间轴已经成立，已有 0.5 ms 边界必须继续披露。

## 唯一公开 Opus 结果与剩余边界

已读取 [公开入口](run_public.py) 的最终原始脱敏回执：选源 `TV_SAMSUNG`、itag 251、实际
decoder 为 Opus、48 kHz 双声道，descriptor 长度 10,258,925 字节。首 PCM 和首次 callback
消费时只取了 262,144 字节；整个前缀加尾部用例共 333,050 字节、两次 Range 请求。
原生 transport 高水位 262,144 字节，双路预留 PCM pool 为 524,288 字节。

seek 请求 634.5 秒，实际首 packet PTS 为 634.374 秒，target 前裁掉 5,736 个转换后帧；
尾部生产和消费均为 3,775 帧，与保留同表示文件的新建 decoder seek 参考 SHA
`e3e11c101250b2bbc6ea90ff14714c649f26fbaad967645378daa7baaa3e1cb9` 相同。
最终 normal EOF、sealed write/read 均为 55,999、ring remaining 为零；旧位置 32,768 帧
因 seek 被明确 discard，不能把全程生产摘要与消费摘要的差异误称丢失尾部。
一个 worker 已 join、一个句柄已释放、设备一启一停；进程用时约 4.415 秒，最高观察 RSS
87,080,960 字节，未触及 256 MiB 观察停止阈值。该阈值不是硬分配器配额。

包含 seek 补充 PCM 的整次观察累计 2,816 个 underflow 帧（48 kHz 下约 58.7 ms）；
当前回执没有按阶段拆分该计数，因此不把全部缺口精确归因到某个回调。
本次不宣称无缝 seek。证据仅为 `prefix then seek-to-tail`，不是全曲连续播放，也不是
把相同 fresh-seek 路径的 SHA 一致提升为绝对采样时间真值。

后续最有区分度的本地边界是 EOF 空读的受控交错、drain 中取消，以及各歧义 padding 组合
的明确拒绝；这些不是重做本轮已有通过所需的重复测试，也不需要人耳录音来验证。

所有本地输出都刻意提交零样本。内容消费、transport、自然 EOF、听觉身份和扬声器首声
是不同证据层；本报告不改变声学校准总误差 unknown，不冻结 30 条可播放语料，也不宣称
Polyhymnia 正式 App 已接入新后端。
