# Streaming v1 独立只读审查

审查对象为已推送提交 **`e42d5fa32e6d3af564991003c978abfef9354829`** 中的
[`streaming/Streaming.cpp`](../streaming/Streaming.cpp)，文件 SHA-256：
`f0fd570dc068fd14e124b22518be6169a5e70cd484ef7e4fcb95ecc7654e2b5e`。
以下行号及行为判断均绑定该版本，不代表正在实现的 v2。

本次仅阅读源码、固定版本 FFmpeg 头文件及既有回执；没有联网、编译、运行音频、
生成测试 scratch 或修改 v1。下列六项是有具体控制流或时间序列依据的发现，
**并非六项均已通过运行复现**。所列触发条件需要由 v2 的独立验收留下新回执。
本文不宣称任何一项已经修复。

v1 的 [原报告](../streaming/README.md) 保留有效范围：本地 AAC/Opus 和公开 AAC
短段实现了完整媒体获取前的解码及静音原生回调消费；原始失败和成功回执继续保留。
这些短观察没有覆盖自然曲终、重采样尾部、后期网络失败、尾部 seek 或活动输出取消，
不能据此推导这些场景通过，也不能推导真实首声或正式产品接入。

## 1. 首输入后期失败可能被汇总为成功

位置：[`done` 的赋值](../streaming/Streaming.cpp#L66)、
[回调的 underflow 判断](../streaming/Streaming.cpp#L100)、
[错误记录](../streaming/Streaming.cpp#L165)、
[最终验收路径](../streaming/Streaming.cpp#L186)。

具体触发：首输入已经通过 `verifyEarly`，随后在等待 next 的新解析或可用时间时，
第二个或后续 Range 请求失败。解码 worker 设置 `error != 0` 后退出，统一令
`done=true`。首输入 ring 耗尽后，回调因 `done` 为真而不再记录 underflow。
next 若正常开始，最终只再次调用 `verifyEarly(next)`，检查 transition 和
underflow 后仍可输出 `streaming_proof=pass`；首输入错误只出现在明细。

这是静态确认的可达误报路径，本审查未注入运行故障。v2 应区分正常 EOF、失败及取消，
在整个会话的结论中检查两路输入的错误和终态。验收应安排“首段已消费后再断第二 Range，
同时延迟 next”，使故障确实发生在第一次早期检查之后；不得只复用首块即断连的旧用例。
失败与中间空缺必须保留，next 成功不得覆盖 first 失败。

## 2. codec drain 后没有排空 SWR

位置：[EOF 分支](../streaming/Streaming.cpp#L162)、
[逐帧重采样](../streaming/Streaming.cpp#L151)、
[直接释放 SWR](../streaming/Streaming.cpp#L166)。

v1 **已经**在 demux EOF 时发送空 packet 并重复 receive；不能把它描述为完全没有
decoder drain。但 receive 不向调用方返回明确的 drain 终态，而此后没有任何
`swr_convert(..., NULL, 0)` 排空过程，便释放 SWR。

具体触发：44.1 kHz 输入转为固定 48 kHz 输出，正常读至 EOF 时重采样器仍持有滤波延迟
样本。释放会丢弃这些尾部 PCM。静态缺失已确认；本审查没有测量丢失的具体帧数。
固定 FFmpeg 8.0 头文件说明 codec 应 receive 至 `AVERROR_EOF`，SWR 则需空输入 flush。

v2 应分别记录 demux EOF、codec EOF、SWR 排空输出帧数及最终返回零，再记录 ring 消费完毕。
验收用带唯一尾标记的 44.1→48 kHz AAC，与相同冻结 FFmpeg 的完整离线转换结果比对。
48→48 kHz Opus 成功不能单独证明采样率转换的尾部已排空。

## 3. seek discard/ack 与旧 PCM 发布有竞态

位置：[producer 复制及发布](../streaming/Streaming.cpp#L41)、
[consumer discard/ack](../streaming/Streaming.cpp#L69)、
[push 前的 generation 判断](../streaming/Streaming.cpp#L154)。

具体时序：producer 通过 generation 检查并进入 `ring.push`，正在复制旧位置的 PCM，
尚未发布新的 `write`；此时 seek 到达，consumer 按旧 `write` discard 并 ack；
producer 随后发布旧块。ring 没有 generation 标签，因此 ack 后仍可能消费旧位置 PCM。
`seek_first_pts` 后来变为目标值，不能证明这些旧样本没有被播放路径消费。

这是并发时序推断，尚未通过暂停点运行复现。最有区分度的验收是在旧块复制与发布之间
设置受控暂停点，确定发生 seek，再释放 producer；断言 ack 后不再消费旧 generation。
修复需建立 producer 已停止发布→consumer discard/ack→worker seek 的顺序，或采用
等价的 generation 可验证协议；在原检查旁简单再读取一次标志不能消除发布间隙。

## 4. 尾部 seek 与解码 EOF 没有一致的完成语义

位置：[seek 接受条件](../streaming/Streaming.cpp#L117)、
[`seekDone` 阈值](../streaming/Streaming.cpp#L155)、
[EOF 后无条件退出](../streaming/Streaming.cpp#L162)。

具体触发有三种：

- 现有 40 秒素材 seek 至约 39.95 秒，剩余约 2,400 个 48 kHz 帧，达不到 8,192 帧阈值，
  因而无法置 `seekDone`，即使已得到正确的全部尾部 PCM。
- worker 已到解码 EOF，但 ring 还留有正在消费的尾部；`!first.done` 条件已经拒绝 seek。
- seek 在 EOF drain 的 receive 期间到达，generation 改变使 receive 退出，EOF 分支却仍
  `break`，worker 结束而未处理该请求。

这些边界尚未在本审查中运行。v2 应把解码完成和 ring 耗尽分开，明确 seek 接受／封口的
原子时点：在不支持的终态及时返回有类型的拒绝，不能接受后等待一个永远不会到达的 ack。
已接受的短尾应允许“已得到所有剩余 PCM”完成准备，不强求固定预填帧数。
验收覆盖小于 8,192 帧的短尾、EOF 与 seek 的受控交错，以及正常曲终只发布一次。

## 5. 流时长被当成绝对结束 PTS

位置：[`duration` 计算](../streaming/Streaming.cpp#L144)、
[按 duration 裁剪 PCM](../streaming/Streaming.cpp#L152)。

具体触发：一个有效流的 `start_time=1s`、`duration=40s`，其时间轴结束在约 41 秒。
当前代码直接在绝对 PTS 40 秒处裁剪，末尾约一秒会消失。固定 FFmpeg 8.0
`AVStream` 定义区分第一帧 `start_time` 和流的 `duration`；后者还可能只是码率估计。

该判断来自代码和类型契约，未生成带偏移的容器复现。v2 应明确时间轴归一化及支持边界，
避免用估计时长静默裁掉有效尾部；尚不支持的偏移应明确拒绝。验收用非零起始 PTS、
未知／估计 duration 和唯一尾标记区分。Opus decoder 的 pre-skip/discard-padding 与
自定义 target trim 应分别核对，不能把目标 PTS 接近请求值当成样本内容正确。

## 6. 活动输出取消没有 callback gate

位置：[取消流程](../streaming/Streaming.cpp#L87)、
[不读取 cancelled 的 callback](../streaming/Streaming.cpp#L97)、
[旧取消用例](../streaming/Streaming.cpp#L176)。

具体触发：输出已经活动时调用 `requestCancel`。设置 session 的取消标志之后，直到
`ma_device_stop` 完成之间，回调仍能消费 ring 并增加内容／时钟计数。旧取消用例是在
设备尚未启动、I/O 正在等待时执行，不能证明活动输出的取消边界。

当前原型始终提交零样本，因此本发现**不声称发生可听声音泄漏**。本审查也未运行活动
取消用例。v2 的回调应在取消后按明确边界停止消费并输出零；验收分别取消正在输出、
producer 因 ring 满而等待、以及 drain 中的会话，核对停止／join、计数终态和资源释放，
不得把取消归类为自然 EOF。

## 最小验收组合与证据边界

1. **本地 Opus 完整尾部**：使用自生成的非周期 PCM，帧数不是 960 的整倍数，末尾包含
   唯一标记；验证 pre-skip/discard-padding 后的帧数及实际 PCM，与冻结的完整离线解码
   参考比较。参考使用同一 FFmpeg，只用于区分流式路径丢帧／重复，不冒称独立解码真值。
   另用 AAC 44.1→48 kHz 覆盖 SWR 尾部。
2. **确定性失败与交错**：后期 Range 断流＋延迟 next、producer 发布暂停点 seek、
   短尾、EOF 封口及活动取消。每次保留失败、取消与未完成状态；实际自然结束需同时
   说明 codec/SWR 已结束和 ring 已耗尽。
3. **一次有界公开 Opus**：v1 的 [公开 first](../streaming/Streaming.cpp#L174) 和
   [公开 next](../streaming/Streaming.cpp#L190) 均硬编码 AAC。新用例必须核实从选择参数、
   descriptor 到实际 decoder 都是 Opus；先验证前缀的原生消费，再按明确策略 seek 近尾
   并 drain。若只消费前缀和 seek 后尾段，就标为 `tail-after-seek`，不能声称全曲连续播放。
   seek 内容正确性需样本／标记对照，不能只比较 `seek_first_pts`。

完整 EOF 验收与“完整媒体获取前已输出”是两个门槛。短素材可能合法地在一次请求中读取
完整文件；不要为了让 EOF 用例通过而把它冒称提前输出。所有静音回调证据仍独立于人耳
内容确认、扬声器首声、30 项可用语料以及正式 macOS App 集成。
