# EDK 1.0 参考工具操作与验收

1.0 是概念算法与参考实现的版本。目前已有软件验证，尚无长期工程验证。下面说明观察研究、六节点初始化、故障复核和离线打包的输入、状态及退出码。环境来源和维护／失养研究是 EDK 核心，节点操作处理辅助电子秘密 KV。

完整概念计算可用 `edk-lab concept-run --seed 2026` 在内存运行，输出检查报告；精确输入 profile 及公开参数见 [算法说明](CONCEPT_ALGORITHM.md)。

## 1. 安装与主机检查

使用发行候选中的 wheel 创建普通用户虚拟环境，按 [部署说明](DEPLOYMENT.md) 离线安装。Linux／树莓派电气条件按 [台架指南](RASPBERRY_PI_BENCH.zh-CN.md) 单独核对。

```sh
edk-lab --version
edk-lab bench-doctor --bus /dev/i2c-1 --check-abi --require-ready --output host-check.json
```

`--require-ready` 要求主机路径／权限／驱动占用检查和原生 ABI 检查都通过，否则退出 3。未加此选项时，doctor 保持诊断命令的兼容行为，成功产生报告可以退出 0。两者均不打开适配器、不扫描地址、不测试电气条件。缺编译器或非 Linux 的 ABI 结果属于未检查。

## 2. 环境实验先声明协议，再采样

建立公开且不含物理秘密的 Anchor Manifest，另建立本地研究协议。协议绑定 Manifest 的公开 fingerprint，指定记录开始时间、最少采样／观察者／时间跨度及读数质量阈值。阈值用于研究可重复性，不是安全熵门槛；示例阈值没有物理验证依据，应在真实实验前按研究问题确定。

按 [观测指南](OBSERVATION_GUIDE.md) 使用非回显终端采集，原始状态留在 0700／0600 的本地私有目录。`study-accept` 从私有记录计算匿名汇总与协议条件结果，不导出状态、观察者身份或会话标识。早于协议时间、不同 Manifest、重复会话或混合来源的输入拒绝接受。软件时间和 `manual` 来源标签可伪造，不能证明真实预登记、独立观察或物理来源。

```sh
edk-lab study-accept my-public-manifest.json --policy my-local-policy.json --store .edk-private --output study-acceptance.json
```

即便质量条件全部通过，`environment_entropy_validated` 和 `real_key_derivation_approved` 仍为 false。没有 Secure Sketch 的情况下，模糊、缺失或改变的输入不会被自动纠正后送入真实 PIN 恢复。

## 3. 单节点公开图案验收

先按台架指南执行 `bench-prepare`／断开主电源的人工试验／`bench-check`。每次独立准备使用新的 token、报告文件名，记录实际测得的 VCC 断开持续时间；软件不推断断电时间，也不证明 SDA／SCL 没有反向供电。

```sh
edk-lab bench-accept trial-1.json trial-2.json trial-3.json trial-4.json trial-5.json --minimum-trials 5 --minimum-vcc-off-seconds 60 --output bench-acceptance.json
```

这里的 5 次／60 秒只是命令示例。全部图案匹配、读前读后 VBATEN 打开、状态稳定、时长已填且达到声明下限，才满足软件条件。不同试验的公开 nonce 必须不同；不能把同一次准备重复读取算作多个试验。PWRFAIL 可保持为 true，其存在不被抹去。

合成与物理工作流记录禁止混合。`physical_io` 是调用流程标签，未认证设备或报告真实性；`physical_acceptance_verified` 始终为 false。零次失败不等于故障概率为零。旧 `bench-check` 的退出 0 仅表示图案匹配且读取中状态稳定，不能代替本验收。

## 4. 六槽位布线配置

从 `examples/hardware-topology.v1.example.json` 建立本地配置，替换为已人工核对的六个独立适配器。索引必须依次 1–6，门限固定为 3，适配器路径不重复。`failure_domain` 使用无地址的抽象代号；真实布线映射和操作目录应保持本地。

```sh
edk-lab topology-check local-topology.json
```

同一声明故障域包含三个节点时退出 3；初始化默认拒绝。操作者可以显式使用 `--allow-colocated-quorum` 记录接受该布局风险。故障域是声明，无法证明实际地点、独立供电或复杂的交叉共同故障。Linux 检查设备 major／minor 和适配器身份仍不能认证芯片，六个地址固定为 0x6f 的独立适配器仍是当前约束；尚无多路复用器驱动。

## 5. 新建实验代次

先确认每个独立空白实验节点的备用供电配置和状态正常。该命令不会自动清除 PWRFAIL、打开 VBATEN 或覆盖已有 EDK1 记录。电源事件需要先保留证据并单独调查，不能靠重试绕过。

```sh
edk-lab hardware-enroll --topology local-topology.json --journal enroll-001.edk-operation --laboratory-hardware
```

操作目录必须不存在，父目录必须已存在且在操作者控制下。新芯片 SRAM 不保证上电清零：只有确认是全新空白硬件时才加 `--initialize-unrecognized`；选项也写入计划。具有 EDK1 头的记录即使损坏仍拒绝覆盖。部分损坏的头部无法可靠识别，所以这个选项不能用作恢复失败后的重试按钮。

步骤固定为：

1. 建立 owner-only 操作目录并同步父目录、持久化计划。
2. 打开并锁定全部六个适配器，核对实际适配器身份和全部 SRAM 可写状态。
3. 只在内存生成 KV 和六份份额，记录公开代次编号。
4. 每个槽位先同步 `write_started`，再执行失效标记／写体／读回／提交／读回；成功后同步 `write_verified`。
5. 重新读取六个节点，比较原份额并在内存验证全部 20 个三节点组合；最后记录 `completed`。

日志只有操作 ID、软件版本、布线配置、时间、公开代次和步骤元数据，不保存 KV、份额负载、秘密哈希、环境状态或 PIN。它不会成为秘密恢复备份。目录权限和文件系统 `fsync` 的正确实现是前提；这不是日志认证、加密存储或实体掉电认证。Python 内存不能保证可靠清零。

## 6. 失败、停机与只读复核

```sh
edk-lab operation-status --journal enroll-001.edk-operation
edk-lab hardware-inspect --journal enroll-001.edk-operation --laboratory-hardware
```

`operation-status` 不做设备事务，也不改日志。`hardware-inspect` 按原计划读取六个槽位，报告元数据是否匹配、当前六份是否一致，不写控制寄存器或 SRAM；I²C 读取仍需发送寄存器指针。

| 记录 | 解释 | 处理 |
|---|---|---|
| `verified_slots` | 该步已完成读回并保存回执 | 保留节点，不自动覆盖 |
| `uncertain_slots` | 已登记写入意图，未有持久化成功回执 | 可能未写、部分写或已提交，只读调查 |
| `not_started_slots` | 本操作未登记该槽位写入意图 | 不代表它物理上空白 |
| `completed` | 六节点最终比较和 20 组合检查均完成并保存 | 后续变化仍需重新检查 |
| 日志损坏／缺页／权限错误 | 历史证据不可采信 | 停止，不能推定未写或重新初始化 |

已提交而回执写盘失败的槽位必须保持 uncertain。当前读数匹配也不会补写历史成功或自动恢复未完成代次。`all_six_consistent_now` 只证明当前这组未认证数据的代数一致性，不能证明原 KV、无复制、无篡改或安全熵。部分初始化没有跨设备原子回滚；重新开始必须经过人工处置，软件没有续写／回滚／重用旧秘密文件的路径。

旧 `hardware-provision`／`hardware-repair` 仍保留实验 API 和兼容性，缺少本流程日志。新初始化应使用 `hardware-enroll`。本轮没有实现带日志的节点替换、份额刷新或撤销；确认损坏与丢失／被盗必须继续区分。

## 7. 自动化退出码

| 命令／情况 | 退出码 |
|---|---|
| 操作完成，或报告条件满足 | 0 |
| 输入／权限／日志／I/O／一致性异常，安全停止 | 2（主 CLI） |
| 已生成有效报告但条件不满足、日志未完成或复核不一致 | 3 |
| 操作者中断 | 130 |
| 发行验收工具失败 | 1 |

合成报告的退出 0 也只表示合成条件满足；必须检查报告来源与明确的证据边界。失败时没有候选 PIN 输出。

## 8. 从公开源码构建发行候选

在 Python 3.11+ 且已安装 setuptools>=77／wheel 的构建环境运行：

```sh
python tools/verify_release.py --output ../edk-1.0.0-candidate
```

工具从公开 allowlist 导出源码，隔离运行普通／优化模式测试，构建并核对 wheel／sdist 的版本、入口、许可证、依赖和源码，独立解包 sdist 重跑测试与重建 wheel，再在全新虚拟环境离线安装、从源码目录之外验证命令。输出 `validation.json`、校验和和分发文件。目录必须是新建的，失败会留下明确失败阶段，不能作为通过的发行包。

源码 ZIP 固定排序和元数据并重打包核对一致性；wheel／sdist 不宣称跨工具链字节一致。原始观测、操作记录、缓存和任意工作目录不进入发行文件；人工粘贴到源码或文档的秘密仍需内容审查。正式 GitHub 上传、tag、Release 需要项目主人另行明确授权。
