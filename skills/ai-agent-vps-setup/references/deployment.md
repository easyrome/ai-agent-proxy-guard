# 部署步骤

以下命令供执行者按现场组合，不能整页直接粘贴。新机器的示例以 Ubuntu Server 24.04 LTS 为基线；已有业务、不同防火墙或不同服务身份时先比较差异。软件核对日期：2026-11-05。OS 生命周期见 [Ubuntu 官方说明](https://ubuntu.com/about/release-cycle)。

## 1. 系统、端口和软件

读取现场状态：

```sh
cat /etc/os-release
uname -m
uname -r
free -h
df -h /
ss -lntup
systemctl status ssh.service ssh.socket xray.service --no-pager
sudo sshd -T
sudo ufw status verbose
sudo nft list ruleset
sysctl net.ipv4.tcp_congestion_control net.core.default_qdisc
timedatectl status
```

某服务不存在可以单独记录，不能因其中一个命令失败而跳过剩余检查。云厂商安全组也属于实际入口链路。检查 443 是否被 HTTPS 服务占用、系统时间是否同步、出口 IPv4/IPv6 是否属于认可范围。保留现有网站等业务，并记录可复测的变更前基线。

| 端口 | 用途 | 处理 |
| --- | --- | --- |
| TCP 443 | VLESS / REALITY / Vision | 基线业务入口；云防火墙与本机防火墙均需匹配。 |
| TCP 22 或现场 SSH 端口 | 管理 | 只开放实际监听端口；有稳定管理来源时可限源，但先证明恢复路径。 |
| UDP 443 | 其他协议可能使用 | 本模板 RAW/TCP 不需要开放这一入站端口。 |
| TCP/UDP 53 | DNS | 使用 VPS 侧受信解析器，不开放公共递归 DNS 服务。 |
| TCP 5201 | 可选 iperf3 测量 | 仅临时、限测试源开放；结束后关闭服务和本次临时规则。 |

代理的 UDP 出站和返回报文由实际协议能力及有状态防火墙处理，不据此放行所有 UDP 入站。不要为了提速扩大暴露面。若采用其他业务端口，后文所有基线 443 都要按实际方案同步到服务端监听、客户端、云防火墙及主机防火墙；REALITY 的目标站点端口则按目标本身设置，不能一并机械替换。

在新机上安装基础工具，先查看 APT 的拟变更和可能触发的服务重启：

```sh
sudo apt-get update
sudo apt-get install openssh-server ca-certificates curl unzip ufw fail2ban nftables unattended-upgrades iproute2 openssl
```

已有防火墙继续沿用，避免 UFW、独立 nftables 管理器和云安全组互相覆盖。Fail2ban 调用 nftables 动态加规则不要求启用一个会重载整个规则集的 `nftables.service`。确认自动安全更新的源、日志与重启策略；不在交互式修复中直接做发行版升级或无人值守重启。

新增或迁移入口时使用 [端口角色与变更验收](ports.md) 的清单，先区分 VPS 公网监听、本机回环入口和测试端口。

## 2. 先保住 SSH

保留当前会话，在另一连接中验证密钥登录以及需要的 sudo 权限。读取 `sshd_config` 的 Include、Match 与实际优先级，再创建本次专用 drop-in；不要假定文件名越靠后越能覆盖已有值。候选设置：

```text
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
X11Forwarding no
MaxAuthTries 3
LoginGraceTime 30
```

`prohibit-password` 仍允许 root 密钥登录。只有已验证普通管理用户及 sudo、新会话和恢复通道后，才按需求进一步禁用 root 登录。不得在没有替代登录证据时关闭现有唯一访问方式。

修改后运行 `sudo sshd -t`，再用 `sshd -T -C user=管理用户,host=目标主机名,addr=管理来源地址` 检查该连接的有效设置。依据实际 service/socket 激活方式应用并验证监听；Ubuntu 的 `ssh.socket` 可能管理监听端口，单看 sshd 文本不足以证明端口变化。参考 [Ubuntu OpenSSH 指南](https://ubuntu.com/server/docs/how-to/security/openssh-server/) 和 [sshd_config 手册](https://manpages.ubuntu.com/manpages/noble/man5/sshd_config.5.html)。

不必为了性能更改 SSH 端口。如确需迁移，先在云和主机防火墙同时放行新端口，保留旧端口，配置并验证新监听、新密钥会话和 Fail2ban 后才移除旧入口。

## 3. 安装可信版本

核对 [Xray 官方稳定发行版](https://github.com/XTLS/Xray-core/releases) 的兼容性及校验材料。编写时验证的版本为 `v26.10.31`，这是可复现的检查基线；未来部署前重新检查安全修复，不能永久锁定旧版。

新机可使用官方安装器。固定来源、下载到文件、检查内容后执行，避免直接把网络响应交给 shell。下面固定的安装器提交来自 [官方仓库](https://github.com/XTLS/Xray-install/tree/04e6f3bd9534811ed901a48c47b2c042dd64eb3a)：

```sh
XRAY_VERSION=v26.10.31
INSTALL_REV=04e6f3bd9534811ed901a48c47b2c042dd64eb3a
curl --fail --show-error --location --proto '=https' --proto-redir '=https' \
  "https://raw.githubusercontent.com/XTLS/Xray-install/$INSTALL_REV/install-release.sh" \
  --output install-release.sh
sha256sum install-release.sh
less install-release.sh
# 检查通过后，仅在已准备好恢复路径的新机执行：
sudo bash ./install-release.sh install --version "$XRAY_VERSION" --without-geodata --without-logfiles
sudo systemctl stop xray.service
/usr/local/bin/xray version
```

本机计算哈希用于记录，不是独立的来源认证。核对安装器实际执行的发行包校验；缺少可信校验材料时记录缺口。已部署机器升级时先保留旧二进制、配置和 unit，候选版本完成配置测试后再安排切换；不要用新机命令覆盖自定义服务。官方安装器提供 `--no-update-service`，但仍需核对其他改动。

## 4. 生成凭据、填充模板

在用户控制的私有目录，使用 `umask 077`，分别运行 `xray uuid`、`xray x25519` 和 `openssl rand -hex 8`。将输出写入权限为 0600 的本地文件；不要把输出、进程参数或订阅链接粘进公共日志。

从 [server-config.example.json](../assets/server-config.example.json) 生成新的候选配置，替换所有 `REPLACE_WITH_` 标记：

- UUID 对应 VLESS 客户端身份，每个使用者独立分配。
- `privateKey` 只保留在服务端。客户端持有匹配的 X25519 派生值；新核心字段名为 `password`，部分客户端仍显示 `publicKey`。它也属于私密连接材料。
- `shortIds` 使用随机、非空、偶数位十六进制值，示例生成 16 位。
- `target` / `serverNames` 使用在 VPS 上验证可达、TLS 1.3 和证书名称匹配的目标。先用 `xray tls ping` 及官方当前要求核对，不把示例域名当可用站点，也不随机扫描目标。

客户端还需要服务器地址、TCP 443、VLESS、Vision、RAW/TCP、REALITY、匹配的 SNI/shortId 和支持的 TLS fingerprint。服务端私钥绝不交给客户端。字段兼容性见 [REALITY 文档](https://xtls.github.io/config/transports/reality.html) 和 [VLESS 入站文档](https://xtls.github.io/config/inbounds/vless.html)。

模板仅监听 IPv4。需要 IPv6 入站时，显式设计监听并单独验证两种地址族；IPv4 监听不等于禁用了 IPv6 出站。模板中的非公网目的地址规则是基础限制，另核对云平台元数据入口及 DNS 解析后实际目的地址；它不是覆盖所有内网访问方式的完整隔离策略。无需下载地理规则数据。

VPS 的 DNS 解析发生在远端，但客户端若先进行本地 DNS 查询仍可能泄漏。把客户端域名解析放到代理路径，另做断线验收。

REALITY 对不合法握手可能转发到 `target`。避免成为无约束的转发入口，检查目标选择、异常流量和服务商额度；按官方要求决定是否需要回落限制，不随意把整条业务链路限速。本站的 REALITY 回落不应变成本地应用的直连备用路径。

## 5. 最小权限与启动

新安装器使用 `xray` 用户；已有服务保留其验证过的专用非 root 身份。核对 `systemctl cat xray.service` 和实际配置位置。候选文件必须可被该服务用户读取：

```sh
sudo /usr/local/bin/xray run -test -config /私有目录/config.candidate.json
sudo install -d -o root -g xray -m 0750 /usr/local/etc/xray
sudo install -o root -g xray -m 0640 /私有目录/config.candidate.json /usr/local/etc/xray/config.json
sudo -u xray /usr/local/bin/xray run -test -config /usr/local/etc/xray/config.json
```

示例安装命令只用于已停服务的新机；在线替换先写同文件系统的临时文件，验证并原子重命名，保留原文件用于恢复。公开模板中的占位凭据必须导致部署检查停止，不允许用固定的公开凭据“先跑起来”。

本模板不做透明代理，通常只需要绑定低端口能力。对照现有 unit 再考虑以下 drop-in，避免继承安装器不必要的网络管理能力：

```ini
[Service]
User=xray
Group=xray
CapabilityBoundingSet=
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
AmbientCapabilities=
AmbientCapabilities=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
Restart=on-failure
RestartSec=5s
```

模板使用服务日志，不写私有 home 或任意配置目录。若现场确需文件日志，单独赋予必要目录写权限；不要为解决权限错误直接去掉全部限制。unit/drop-in 变更后执行 `systemctl daemon-reload`；防火墙就绪且配置检查通过后，新机执行 `systemctl enable --now xray.service`，已有服务在维护窗口按实际 unit 重启。核对 `systemctl status`、`journalctl -u xray.service`、实际监听和 `systemctl show` 的有效属性，配置测试和实际请求都要通过。

## 6. 防火墙与 SSH 封禁

仅在新机且已确认实际 SSH 端口后，设置 UFW 默认拒绝入站、允许出站，先加管理端口和 TCP 443，再启用。已有机禁止执行 `ufw reset`。同时确认 `/etc/default/ufw` 的 IPv6 管理状态、云规则、回包状态规则及必要的 ICMP/ICMPv6；全丢 ICMP 会破坏路径 MTU 等功能。

Fail2ban 的本次专用 jail 可从下面起步，`ACTUAL_SSH_PORT` 必须替换；若 SSH 日志不在 systemd journal，改用经验证的日志后端：

```ini
[sshd]
enabled = true
backend = systemd
port = ACTUAL_SSH_PORT
banaction = nftables-multiport
maxretry = 5
findtime = 600
bantime = 3600
bantime.increment = true
bantime.maxtime = 86400
ignoreself = true
ignoreip = 127.0.0.1/8 ::1
```

运行 `fail2ban-client -t` 再应用，检查 `fail2ban-client status sshd` 和实际 nftables 规则。此 jail 只保护 SSH；不要因管理登录失败而把代理业务 443 也封禁。测试封禁使用保留的文档测试地址并立即解封，不拿当前管理来源做实验。配置语义见 [Fail2ban 官方示例](https://github.com/fail2ban/fail2ban/blob/master/config/jail.conf)。

基础内核加固保留用户态代理的 forwarding 关闭状态；禁用不需要的 redirects/source routing 时分别核对 all/default/现有接口，记下旧运行值。涉及 rp_filter、容器、策略路由或多网卡时按拓扑判断，不能盲目套用严格反向路径过滤。

随后进入 [验证与恢复](verification-recovery.md)，再决定是否需要 [性能调整](performance.md)。
