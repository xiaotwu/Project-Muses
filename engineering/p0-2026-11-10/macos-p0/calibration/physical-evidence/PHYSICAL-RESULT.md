# 本轮声学检查结果

两份已完成摘要均为 **`measurement_invalid` / `sequence_not_matched`**，没有匹配标记；不能计入 `t_sound`、首声延迟、测量误差门槛或成功的基线尝试。失败原因尚未确定，不根据音量、采样率或时钟拟合残差推断原因。

| 现有记录 | capture start/stopped 单调时钟间隔 | 保存到内存的输入样本 | 结果 |
| --- | ---: | ---: | --- |
| [run 1](calibration-1-241196932756541.json) | 6.065077750 s | 283,200 帧，48 kHz，对应 5.9 s | `sequence_not_matched` |
| [run 2](calibration-2-241244703078208.json) | 6.067544583 s | 283,200 帧，48 kHz，对应 5.9 s | `sequence_not_matched` |

两份摘要的输入和输出均记录为内建设备、48 kHz；输出音量标量约 0.125，输入约 0.525，`clipped_fraction=0`。这些是条件记录，不是因果结论。两份 `markers` 均为空，`total_physical_error_bound_ms` 均为 null，`baseline_attempt=false`、`raw_audio_saved=false`。采集起止间隔、PCM 样本时长与实际可听声音是不同观测；没有把它们互相替代。

## 用户听感与发起归属

保留反馈的先后顺序：

1. 用户最初反馈“没有听到，或不确定”。
2. 用户随后补充，刚才能听到两个“哔”的声音，并询问是否为所说的提示音。Root 回答很可能是该工具间隔约 2.5 秒的两段短声。

第二条是人工听感补充；不能据此确认对应 run 1 还是 run 2，也不能将其标为麦克风匹配成功或毫秒级首声测量通过。没有为核对这条反馈新增播放或录音。

本轮实际观察到了两份完成摘要，但不声称 root 发起了两次采集。Root 的一次后续 CUA 点击受到界面中的用户变更阻止，此后才观察到 run 2 已完成；本附录不推断第二份记录的发起者。记录汇总和原始文件哈希见 [physical-summary.json](physical-summary.json)。

## 退出过程与当前状态

以下先后过程由 root 的前台检查记录提供：

1. App 菜单为空，Cmd+Q 没有生效；当时的 window-sharing 视图也没有暴露原生关闭入口。
2. 两次采集都已完成后，root 对核验过可执行文件的精确 PID **93220** 发送 SIGTERM。[原始 process-stop.json](process-stop.json)记录了这一阶段，没有修改。
3. 后续 `getAXState` 验证意外重新打开了处于 idle 状态的 app；没有启动新采集。
4. Root 随后使用新状态中出现的原生关闭按钮退出；`cua.getState` 不再列出该 app。
5. 本附录另用只读 CLI `ps -axo pid=,comm=` 核对，未发现 `MusesAcousticCalibration` 进程，见 [附加进程回执](CLI-PROCESS-CHECK.json)。该查询没有启动 app、请求权限或发起采集。

后续进程存在性核对应使用 CLI，避免 `getApp` / AX 查询再次自动打开应用。这里的“无进程”仅是查询时点的结论，不表示系统残留全部清理。

TCC 权限、应用注册及必要摘要／缓存仍作为暂停依赖保留；临时目录和系统残留的统一核对由 root 的 Stage 6 收尾负责。本次仅新增本目录的说明、派生汇总和只读进程回执，没有修改冻结源码、旧 manifest、原两份摘要或 `process-stop.json`，也没有改变系统音量、设备或 scratch。

校准工作现暂停，优先继续 Mac 播放本体。未来候选需要补标准 Quit 入口和不发声的输出链路诊断，再决定是否需要另一次用户许可的声学检查；本附录不安排新录音。
