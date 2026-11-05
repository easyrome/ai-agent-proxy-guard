# 性能、端口与稳定性

## 先定位哪一段慢

端口号不携带带宽。TCP 443 是本方案的默认业务入口；换到高位端口只有在原端口冲突、过滤、整形或实测路径差异时才有理由。即使 8443 在某次更快，也要在相同时段、相同目标和同样配置下复测，不为试速长期开放一串端口。

把连接分为本地网络、客户端代理、跨境链路、VPS、VPS 到目标五段。历史案例中既出现过跨境连接尖峰，也出现过客户端 DNS 间歇失败，不能都归因于服务器端口。

| 观察 | 进一步区分 |
| --- | --- |
| 本地网关延迟也抖动 | Wi-Fi、上传占满、本机队列；用有线或已获准的另一网络作对照。 |
| TCP 建连、TLS 或首字节慢 | 同目标重复测，分清显式代理、TUN、DNS 与服务端连接阶段；超时不能删除后再算“平均速度”。 |
| VPS CPU / steal / 内存异常 | `vmstat 1 10`、`free -h`、`journalctl`；检查宿主机争用、OOM 与服务重启。 |
| 建连快，持续传输慢 | VPS 带宽、线路拥塞、对端限速、接收窗口与磁盘；先排除小文件握手占比。 |
| 只有某个应用失败 | 核对应用自身代理、进程、DNS、认证与流量出口；不要只凭通用测速下结论。 |

`ss -ti` 的 retrans 往往是连接累计值，不能直接除以连接数称为丢包率。中间路由器不答 ICMP 也不能独立证明该跳丢包。保留采样窗口、方向、连接身份和对照。

## 小流量、可重复测量

附带脚本需要 Python 3.10+、curl 8.4+，使用 HTTPS 校验，不跟随重定向。每次启动全新 curl 进程，默认测 10 次，每次最多取 64 KiB，输出匿名化 JSON。选择用户认可的、大小合适的静态 HTTPS 文件；大文件或忽略 Range 的服务可能触发字节上限，这应当记为失败，不能冒充带宽不足。

```sh
python scripts/measure_https.py --url https://your-measurement-host.example/small-file \
  --proxy socks5h://127.0.0.1:10808 --count 10 --output before.json
```

端口要替换为实际的专用本地代理入口。HTTP 代理也可使用 `http://127.0.0.1:实际端口`。脚本没有上游选择能力：先证明该入口确实固定到待测 VPS，尤其在使用分流、自动选择或多个节点时。它也不能证明代理核心内部没有直连回退。

脚本显式代理失败后不会改用直连，并忽略环境中的代理设置和 curl 用户配置。若需要同目标直连对照，显式传 `--direct`；它会把本机网络地址暴露给该测量端点，因此只对已授权的测试目标使用。不要让受保护 AI Agent 借此绕过断线保护。

```sh
python scripts/measure_https.py --url https://your-measurement-host.example/small-file \
  --direct --count 10 --output control.json
```

`status=measured` 且退出码 0 表示全部 HTTP 样本完成；任何请求失败或非 200/206 状态都会得到 `status=incomplete`、退出码 2 和失败数。成功样本的 p50/p95 必须与总样本数、失败数一起解读。参数错误退出码 1。结果不输出目标地址、远端 IP、响应正文或凭据。

`connect_seconds` 在代理模式下主要反映到本地代理的 TCP 连接；其后阶段还包含代理握手、远程连接和 TLS，不能称为“到德国的 RTT”。`small_object_bytes_per_second` 包含建连开销，只用于相同小文件的对照，不能代表持续带宽。缓存、压缩、目标大小与时间段变化均可能影响比较。

低样本 p95 只是当前窗口估计。至少保留调整前后同量样本，并在用户常用的繁忙时段复核。持续带宽有必要时再使用受控的大文件或临时限源 iperf3，预先计算时长和数据额度；其直达链路结果也不能代替通过代理的 HTTPS 结果。相关 curl 选项见 [官方手册](https://curl.se/docs/manpage.html)。

## BBR 与队列

先只读检查：

```sh
sysctl net.ipv4.tcp_available_congestion_control
sysctl net.ipv4.tcp_congestion_control
sysctl net.core.default_qdisc
ip route show default
tc qdisc show
ss -ti
```

发行版内核支持 BBR 时才使用；必要时加载发行版提供的 `tcp_bbr` 模块。模块不可用时保留受支持内核和当前算法，不默认安装第三方“加速内核”。

对新机或已获准的调整，记录两个键的旧运行值和同名 drop-in 的旧内容/是否存在，再写独立配置：

```ini
# /etc/sysctl.d/90-agent-network.conf
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr
```

使用 `sysctl -p /etc/sysctl.d/90-agent-network.conf` 仅加载本次文件，避免 `sysctl --system` 意外带入其他待生效变更。检查所有 sysctl 配置的优先级，防止下次启动被其他文件覆盖。官方语义见 [Linux TCP sysctl](https://docs.kernel.org/networking/ip-sysctl.html) 和 [默认队列设置](https://www.kernel.org/doc/html/latest/admin-guide/sysctl/net.html)。

新拥塞算法用于新连接；已有连接需要另外判断。更改 `default_qdisc` 不会自动替换已经存在的网卡队列。用 `tc qdisc show dev 实际网卡` 看实际 root/leaf，虚拟网卡可能是 `noqueue`，多队列设备可能有 `mq` 和各自叶子。已有流量整形、云网络约束或复杂队列时不要直接 `tc qdisc replace ... root fq` 覆盖。参阅 [fq 手册](https://man7.org/linux/man-pages/man8/tc-fq.8.html)。

维护窗口内可选择有备份的精确队列调整或重启后验证；不能重启时分别报告已生效的新连接算法、当前队列与重启后待验证项。服务器只决定自己的发送侧策略，不能保证整个往返路径改善。

## 调优停止条件

每次只改变端口、拥塞控制、队列或其他一个主要因素。若成功率下降、p95 明显恶化、SSH 不稳或出现新的错误，先恢复本次差异再继续定位。

没有测到持续改善就保留简单基线。大 buffer、关闭时间戳/SACK、极短超时、激进重试、盲目 MTU 修改和多层中转都不是默认加速项。PMTU 问题先证明报文尺寸相关失败并核对 ICMP；重试应有限次、带退避，不能把拥塞或泄漏掩盖成“恢复”。

如果瓶颈是运营商到 VPS 的线路或宿主机争用，本机参数可能无法解决。报告证据与仍未知的环节；用户选择保留某地区节点时继续在该范围内优化，不擅自切换地区或添加未经认可的备用出口。
