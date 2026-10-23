# Linux／Raspberry Pi 单节点台架

选定路径：Linux 主机读写，不依赖 MCU 固件。版本 0.2.0a1 增加主机检查、公开测试图案的写入与掉电后读取、原生 Linux ABI 检查。当前未连接树莓派或实体 MCP7940N，以下是可执行的联调流程，不能作为已完成实测。

## 1. 先确认板卡与供电

本指南针对具有标准 GPIO 接口的 Linux Raspberry Pi。Compute Module、自制底板或其他 Linux 主机需按自身原理图映射信号，不套用接口位置。首轮只连接一块确定用途的实验板，不连接保存真实秘密的节点。

| 主机信号 | 实验节点信号 | 要点 |
|---|---|---|
| GPIO2 / SDA | MCP7940N SDA | 确认实际接口标识；信号上拉到 3.3 V |
| GPIO3 / SCL | MCP7940N SCL | 与 SDA 一样检查上拉电源与总线冲突 |
| GND | VSS / 公共参考 | 主机、主电源和备用电源需要明确参考 |
| 经过独立开关的稳压主电源 | VCC | 在芯片端测量，不以主机供电状态代替 |
| 经审核的独立备用储能电源 | VBAT | 不与 VCC 开关一起切断；遵守器件电气范围 |

Raspberry Pi 的 GPIO 是 3.3 V 信号域，不能把带 5 V 上拉的模块直接接入。GPIO2/3 的上拉也可能使断电节点经信号线被反向供电。上表是信号关系，不是完整充电、隔离或保护电路；未知型号的 RTC 模块可能已有电池、二极管或充电电阻，必须先检查原理图和器件标识。

主机接口与 GPIO 信息依据 [Raspberry Pi 官方硬件文档](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio-and-the-40-pin-header)。芯片供电、管脚与备份行为依据 [Microchip DS20005010J](https://ww1.microchip.com/downloads/en/DeviceDoc/MCP7940N-Battery-Backed-I2C-RTCC-with-SRAM-20005010J.pdf)。实际板卡映射、上拉和隔离尚待测量确认。

## 2. 配置 Linux，并先做无事务检查

在 Raspberry Pi OS 使用 `sudo raspi-config`，选择 Interface Options → I2C 启用接口；版本菜单差异以[官方配置文档](https://www.raspberrypi.com/documentation/computers/configuration.html#enable-or-disable-i2c)为准。不要为这个应用自动加载 RTC overlay；已绑定的 RTC 内核驱动会与用户态写入冲突。

按部署指南创建虚拟环境并安装 wheel，然后运行：

```sh
edk-lab bench-doctor --bus /dev/i2c-1 --output pi-host-check.json
```

这个命令不会打开 I²C 设备，不扫描地址，不发送 ioctl 或设备事务。它检查运行平台、节点类型、Linux I²C 主设备号 89、读写权限以及 0x6f 是否绑定内核驱动；报告不含主机名、MAC、序列号或访问凭证。`host_preflight_passed` 仅表示这些主机条件，不表示接线、电源、芯片身份或总线功能已通过。

`/dev/i2c-1` 是常见示例，不保证所有型号/启动配置都相同。可查看 `/sys/class/i2c-dev/` 或 `i2cdetect -l` 列出适配器；这里的 `-l` 是列表，不是地址扫描。访问权限按实际系统设备节点与组配置处理，不用 `chmod 666` 暴露整个总线，也不默认让整个应用以 root 运行。Linux 接口依据[内核文档](https://www.kernel.org/doc/html/latest/i2c/dev-interface.html)。

## 3. 检查实际 Linux ABI

可选择在主机检查中运行编译探针：

```sh
edk-lab bench-doctor --bus /dev/i2c-1 --check-abi --output pi-host-and-abi.json
```

或者从源码目录运行：

```sh
python tools/check_linux_abi.py --require
```

需要目标机的 C 编译器和 Linux UAPI 头文件（Debian/Raspberry Pi OS 通常由 `build-essential`、`linux-libc-dev` 提供）。工具只编译固定的结构体布局程序并执行，不访问设备。比较 `i2c_msg` / `i2c_rdwr_ioctl_data` 的大小、指针偏移和 ioctl 常量，适用于本机 32/64 位 ABI；它不能验证驱动、板卡或电气行为。`--require` 在无法执行时返回 2，不把跳过当成通过。当前 macOS 开发环境会明确报告 Linux required。

## 4. 首轮只写公开测试图案

确认节点是专用实验板，主电源稳定、备用电源与模块电路正确，主机检查无冲突后：

```sh
edk-lab hardware-probe --bus /dev/i2c-1 --laboratory-hardware
edk-lab bench-prepare --bus /dev/i2c-1 --token public-test-001.json --enable-backup --laboratory-hardware
```

若全新芯片 SRAM 是未初始化的随机内容，需要在检查用途后显式加 `--initialize-unrecognized`。该选项仍不会覆盖任何以 `EDK1` 开头的份额记录，即使其校验和已损坏。已识别的公开 `EDKT` 测试图案可以被下一轮测试替换。

准备操作先保留新的公开 token 文件，然后失效标记、写入测试记录、读回校验并提交。token 只有公开 nonce、格式与创建时间，足以重建测试图案；它不是 KE、KV、真实份额或 PIN，也不是“准备已经成功”的凭证。失败后 token 可能仍然存在，必须根据命令结果与再次读取判断状态。现有 token 文件不覆盖。

备份尚未启用时，`--enable-backup` 会显式修改 RTCWKDAY。若已有掉电标志则拒绝这一修改，以免自动清除事件证据；新的实验可以保留标志进行读取。软件不启动振荡器、不设置时钟。准确 RTC 掉电时间戳需要另外核实振荡器与时钟设置；首轮时长由外部计时提供。

基线读取：

```sh
edk-lab bench-check --bus /dev/i2c-1 --token public-test-001.json --report baseline-001.json --laboratory-hardware
```

## 5. 主电源中断与恢复

1. 记录主电源、备用电源、芯片端电压和环境条件，保存基线读取结果。
2. 在经审核的电路上隔离可能反向供电的 SDA/SCL 等通路，切断目标节点 VCC，保持独立 VBAT；不要只拔一个标称电源就假定芯片已经失去主电。
3. 在芯片端确认实际电压和持续时间。备用状态下不进行 I²C 访问；CPU 电压或树莓派运行时间不能代替芯片 VBAT 测量。
4. 先恢复稳定 VCC，再恢复已验证的通信连接，然后读取同一个公开 token：

```sh
edk-lab bench-check --bus /dev/i2c-1 --token public-test-001.json --vcc-off-seconds 60 --report after-001.json --laboratory-hardware
```

`60` 是操作员提供的外部计时值，软件不会把两次命令的墙钟间隔当作真实断电时长。报告明确保留这一来源，不填造温度、电压或保持时间。`bench-check` 不写 SRAM 或控制寄存器、不清除 PWRFAIL；I²C 随机读取仍会发送寄存器指针地址，因此“只读”不等于线上没有写方向消息。

报告只有公开图案是否匹配、公开测试 nonce、读取前后状态、观察时间和操作员提供的时长；不输出实际 SRAM 内容、其哈希、真实份额或 PIN。匹配且状态稳定时返回 0；不匹配或读取中状态改变时仍保存观察报告并返回 3；无效输入/不可用 I/O 返回 2。

图案相同只说明这一次读取仍与预期一致，不能推断多年的保持寿命。不匹配也不证明历史信息已经物理消失，更不证明安全擦除。PWRFAIL 本身不是电压证明。

## 6. 无实物时复现软件流程

```sh
edk-lab bench-demo
python -m unittest discover -s tests -v
```

`bench-demo` 的输出明确标记 SIMULATED，使用内存总线模拟保留、掉电标志和逻辑丢失，不访问实体元件。自动测试覆盖写入前缀中断、拒绝份额覆盖、状态变化、错误 token、只读检查、构造器清理与 ABI 比较；原生 Linux 编译检查仍需在目标机或 Linux CI 上实际执行。

## 7. 从单节点到六节点

先完成一个节点的基线、主备电源切换、反向供电和保持试验，再重复到独立样本。当前 `hardware-provision` 仍要求六个不同适配器身份，并不把同地址芯片并接到一个总线，也没有实现复用器。不能用一台台架或一个备用电池的结果证明六节点在地理、供电与攻击域上独立。

后续真实 EDK 集成仍需要环境熵来源、稳健恢复、认证份额/读写端和独立审查；选择 Linux 路径不改变这些要求。Linux 主机是本轮目标主控，不再把新增 MCU 固件作为推进这条路径的前置条件。
