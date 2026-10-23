# Environment-Derived Key · EDK 1.0

[English](README.en.md)

**EDK 是研究“现实环境、持续维护与秘密存续之间关系”的概念算法。1.0.0 提供算法参考实现、实验工具、易失性节点读写程序及数学模型；目前完成的是软件验证，尚未进行长期工程验证。**

## 核心思想

EDK 将恢复能力绑定到两个来源：现实物理环境的状态信息，以及易失性电子节点保存的独立随机秘密。主人维护环境和节点时，可以保持可恢复性；维护停止后，如果原始物理信息逐渐流失、电子份额逐渐失效，恢复所需的信息也会减少。

这里研究的是给定攻击者知识、设备、时间和资源条件下的恢复概率。已经复制的历史信息会继续存在；纠错失败本身也不能说明原始信息已经消失。环境的实际安全贡献取决于条件不可预测性，而不是可表示状态的数量。

## 算法结构

```text
现实物理锚点 ──读取与编码──> 环境输入 E ───────┐
                                             ├─ HKDF-SHA256 ─ 拒绝采样 ─ 12 位 PIN
六个易失节点 ──3-of-6 恢复──> 随机秘密 KV ────┘
                         公开参数：Manifest、盐值、设备上下文
```

环境输入与电子秘密都参与派生。电子节点负责第二秘密源和维护机制；真实环境负责第一来源。公开的房间名称、地址或设备摆放位置不能替代有实际不可预测性的环境状态。

1.0 的精确输入 profile 为 `edk.exact-input/v1`：

```text
E   = Encode_v1(Manifest, exact_observations)
KV  = ShamirRecover(shares, threshold=3)
PIN = derive_pin(E, KV, salt, device_id)
```

编码包含完整 Manifest 的公开指纹、锚点数量和按顺序排列的读数。每个锚点可定义 2–65536 种状态。正常读数按规则编码，模糊或不可读状态返回错误。该 profile 采用精确匹配，Secure Sketch／Fuzzy Extractor 属于后续研究。

Manifest 的名称、规则文字、状态数量和顺序都影响编码；登记后需要保留同一份 Manifest、公开盐和设备上下文。读取时间、观察者和会话编号不参与派生。详见 [算法说明](docs/CONCEPT_ALGORITHM.md)。

## 快速运行

要求 Python 3.11+，运行时使用 Python 标准库。

```sh
python -m pip install -e .
edk-lab --version
edk-lab concept-run --seed 2026
python -m unittest discover -s tests -v
```

`concept-run` 用合成观测在内存执行完整参考流程：比较全部 20 个三节点组合，检查损坏份额修复，并检查缺少环境、模糊读数、不可读状态、不足门限和混合代次的处理。输出为 JSON 检查报告；同一种子生成相同的合成输入与派生结果，份额多项式另行随机生成。

源码包也可以构建为 wheel 后离线安装：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --no-deps /path/to/edk_lab-1.0.0-py3-none-any.whl
.venv/bin/edk-lab concept-run --seed 2026
```

原有 `demo` 命令保留 40×64 原始字节输入示例，并显示合成 PIN；`concept-run` 使用新的 Manifest 绑定 profile，输出检查结果。

## 实现内容

| 部分 | 1.0 实现 |
|---|---|
| 概念算法 | 精确观测编码、3-of-6 恢复、HKDF-SHA256 与 12 位十进制映射 |
| 环境实验 | 版本化 Anchor Manifest、非回显采样、私有记录、重复性／缺读率／时间／相关差异分析 |
| 实验验收 | 预先声明的样本、观察者、跨度及质量阈值，匿名汇总报告 |
| 生命周期模型 | 节点独立与相关故障、车辆应力、维护与停止维护、环境读错／擦除／历史信息流失 |
| 电子节点 | MCP7940N 64 字节记录、Linux I²C 读写、读回检查与损坏份额重建 |
| 操作流程 | 六槽位配置、写前日志、逐节点回执、部分失败记录、只读复核 |
| 数学与验证 | 门限性质、条件擦除模型、PIN 映射和提交顺序论证，有限模型检查及软件测试 |
| 发行工具 | 公开源码导出、wheel／sdist 构建核对、sdist 重建、独立环境离线安装验收 |

Shamir 份额的 CRC 用于检测意外错误，份额和读写器认证尚未实现。新 profile 编码后直接交给现有 KDF，不对环境熵作估计，也没有增加容错提取机制。

## 环境采样与生命周期实验

```sh
edk-lab manifest-check examples/anchor-manifest.v1.public.json
edk-lab synthetic-study examples/anchor-manifest.v1.public.json --count 30 --seed 2026 --store .edk-private
edk-lab analyze examples/anchor-manifest.v1.public.json --store .edk-private --output study.aggregate.json
edk-lab simulate-lifecycle --months 36 --trials 1000 --seed 2026 --maintenance-every 1 --output lifecycle.synthetic.json
```

实际人工采样使用 `collect`。原始状态保存在本地 0700／0600 权限目录中，公开报告只含聚合统计。研究记录与真实密钥登记分开使用，EDK 的维护依赖设计不设置永久环境秘密备份或万能恢复通道。

`study-accept` 按研究协议计算质量结果，`bench-accept` 检查公开图案试验记录。可重复读取与低缺读率描述可用性；环境安全贡献还需要攻击者知识和来源分布的研究。

## Linux／树莓派节点程序

当前主控路线为 Linux／Raspberry Pi I²C，候选器件为 MCP7940N。每份记录占用 64 字节电池备份 SRAM，六节点方案使用六个独立适配器。

```sh
edk-lab bench-doctor --bus /dev/i2c-1 --check-abi --require-ready
edk-lab topology-check examples/hardware-topology.v1.example.json
```

节点初始化使用 `hardware-enroll`：全节点预检后生成 KV，逐节点保存写入意图和读回回执，最后检查全部门限组合。`operation-status` 查看日志，`hardware-inspect` 只读复核当前节点状态。部分失败保留不确定状态，没有自动续写或跨节点回滚。

硬件接线、供电切换和保持时间的实物测试仍待开展。操作步骤见 [工程运行手册](docs/ENGINEERING_RUNBOOK.zh-CN.md)、[树莓派台架指南](docs/RASPBERRY_PI_BENCH.zh-CN.md) 和 [SRAM 分析](docs/SRAM_ENGINEERING.md)。

## 验证进展

已有软件测试覆盖 GF(256)、Shamir、RFC 5869 向量、输入格式、精确 profile、异常状态、写入中断、操作日志和发行文件。实际运行结果及测试数量随包保存在 `validation.json`，构建流程如下：

```sh
python -m pip install "setuptools>=77" wheel
python tools/verify_release.py --output ../edk-1.0.0-candidate
```

目前尚无长期环境跟踪、实物供电／保持时间曲线、物理残留恢复实验或目标键盘设备联调结果。环境条件最小熵、容错恢复、认证与代次刷新、外部数学和工程审查列为后续工作。现有数学证明给出明确模型和假设；软件测试与物理结论分别记录。

## 版本与兼容性

`1.0.0` 表示本次概念算法与参考工具的版本。JSON `/v1`、`EDK1` SRAM 格式和 KDF 域 `EDK-LAB/v0.1-alpha` 各自独立管理。旧原始字节接口的有效输入向量保持不变；新精确 profile 使用不同的环境编码，因此两类输入不共用 PIN 向量。

本目录为本地发行源码。GitHub 上传、tag 和 Release 状态由实际发布记录确定。

## 文档与目录

- [算法与接口](docs/CONCEPT_ALGORITHM.md) · [架构](docs/ARCHITECTURE.md) · [数学模型](docs/FORMAL_SPEC.md)
- [环境实验](docs/EXPERIMENTS.md) · [观测工具](docs/OBSERVATION_GUIDE.md) · [后续工作](docs/ROADMAP.md)
- [部署](docs/DEPLOYMENT.md) · [威胁模型](docs/THREAT_MODEL.md) · [安全说明](SECURITY.md) · [版本记录](RELEASE_NOTES.md)

```text
src/edk/   算法、观测、仿真、节点读写与操作流程
tests/     单元与故障测试
examples/  公开结构示例和合成结果
docs/      数学、设计、实验与工程文档
tools/     发行构建和核对
```

许可：[MIT](LICENSE)。
