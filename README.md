# AI Agent 代理保护与 VPS 部署

让指定 AI Agent 只能通过认可的代理出口访问公网。VPS 失联或客户端退出时，新请求应当失败。其他应用的影响取决于保护范围：指定应用隔离可以保留其他应用分流；整个浏览器固定到本机代理时，代理退出也会影响该浏览器的其他公网网站。

本仓库提供两个可独立安装的 Agent Skills：

| 技能 | 用途 |
| --- | --- |
| [ai-agent-proxy-guard](skills/ai-agent-proxy-guard/SKILL.md) | 找出实际联网进程，配置本机出口约束，验证分流、DNS、WebRTC 和 IPv6。Windows 有具体示例与只读采样器。 |
| [ai-agent-vps-setup](skills/ai-agent-vps-setup/SKILL.md) | 部署和维护 Linux VPS 出口：系统、软件、业务端口、SSH、防火墙、BBR、测速与恢复。附服务端配置模板及有流量上限的 HTTPS 测量脚本。 |

VPS 技能以 Ubuntu Server 24.04 LTS、Xray、VLESS + REALITY + Vision、TCP 443 为基线。SSH 使用读者自己服务器的实际端口；新系统通常为 TCP 22。端口选择和 BBR 调整必须经过前后测量，不能保证任意线路提速。

## 最近更新：2026-11-07

- 固定出口、受保护进程/域名与专用 DNS 规则优先于普通分流和模式切换；同时核对持久模板与生成配置，防止重载后失效。
- 补充日常浏览器的实际策略核验、WebRTC 扩展与策略共同作用、CSP 对测试的影响，以及独立恢复和严格故障时间窗。
- [端口角色与变更验收](skills/ai-agent-vps-setup/references/ports.md)区分 VPS 业务端口、本机代理入口、TUN 辅助入口和临时测试端口。
- [本次现场验证摘要](docs/validation-2026-11-07.md)记录 36 次隔离负向请求、日常浏览器 43 次故障内 HTTP 请求、51 次 WebRTC 采样和 API 补测，同时保留未验证项。摘要整理既有实测证据，本次文档更新没有重新中断生产网络。

## 安装

支持 Agent Skills 的工具可按上表路径安装任一技能。手动安装时，把所需技能的整个目录复制到工具的技能目录中。以下以 `ai-agent-proxy-guard` 和用户级目录 `~/.agents/skills/` 为例；安装 VPS 技能时把示例中的技能名改成 `ai-agent-vps-setup`，仓库地址与克隆目录保持不变。若目标同名目录已存在，先比较版本。

**Windows PowerShell**

```powershell
git clone https://github.com/easyrome/ai-agent-proxy-guard.git
if ($LASTEXITCODE -ne 0) { throw 'Clone failed' }
$skillRoot = Join-Path $HOME '.agents/skills'
$target = Join-Path $skillRoot 'ai-agent-proxy-guard'
if (Test-Path -LiteralPath $target) { throw 'Skill already exists' }
New-Item -ItemType Directory -Path $skillRoot -Force | Out-Null
Copy-Item -LiteralPath './ai-agent-proxy-guard/skills/ai-agent-proxy-guard' -Destination $target -Recurse
```

**macOS / Linux**

```sh
git clone https://github.com/easyrome/ai-agent-proxy-guard.git &&
  mkdir -p "$HOME/.agents/skills" &&
  test ! -e "$HOME/.agents/skills/ai-agent-proxy-guard" &&
  cp -R ai-agent-proxy-guard/skills/ai-agent-proxy-guard "$HOME/.agents/skills/"
```

打开一个新会话，发送下面这句话。第一轮可以在代理保持正常运行的情况下进行。

> 用 $ai-agent-proxy-guard 检查指定 AI Agent 的出口。先只读核对实际联网进程、分流、DNS、WebRTC 和 IPv6，告诉我哪些已有证据、哪些还需要断线测试。

安装 VPS 技能后可发送：

> 用 $ai-agent-vps-setup 部署我的 VPS。先核对现有系统、SSH 和业务，给出所需软件与端口；保留恢复路径，再完成配置、客户端验证和性能对照。

仅想诊断慢速时可以明确“先只读测速，不修改线上配置”。服务端模板必须在私有环境生成独有凭据；它不是可直接部署的公共账号。

## 验收要看什么

| 现场情况 | 期望看见的行为 |
| --- | --- |
| 代理正常 | 真实应用的新请求经批准的出口成功，独立的直连对照也能工作。 |
| VPS 上游失联，但本机代理仍监听 | 所有能承接受保护流量的上游确实不可用；受保护请求在故障窗口内无法完成，不得切到直连或未经认可的备用节点。 |
| 管理器、核心和 TUN 全部退出 | 同一应用发出的新请求失败；同时查系统是否拦截了该应用的直连尝试。 |
| 仅 TUN 停止，本机代理仍可用 | 显式代理路径可以继续工作。绕过它去物理网络的尝试应被阻止。 |

故障中排队、恢复后才收到回复，须按时间分开记录。CLI、桌面应用、浏览器和 DNS 解析器各自取证。查看 [技能入口](skills/ai-agent-proxy-guard/SKILL.md)。

分流方法参考 [AgentRoute](https://github.com/ryuu-restart/agent-route)，本仓库不分发其规则名单。VPS 技能的参考文件包含对应上游官方文档。原创技能与辅助脚本以 [MIT 许可证](LICENSE)开放使用。
