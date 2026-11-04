# AI Agent 代理断线保护

让指定 AI Agent 只能通过认可的代理出口访问公网。VPS 失联或客户端退出时，新请求应当失败；其他应用仍可按自己的分流规则联网。

这是一个可安装的 Agent Skill。它指导执行者找出实际联网的进程、配置本机出口约束，并分别验证分流、DNS、WebRTC 和 IPv6。Windows 原生应用有具体操作示例，其他平台按可用隔离能力适配。附带的 Windows 采样器只读本机连接表。

## 安装

支持 Agent Skills 的工具可从本仓库安装 `skills/ai-agent-proxy-guard`。手动安装时，把这一整个目录复制到工具的技能目录中。以下是用户级目录 `~/.agents/skills/` 的例子。若目标同名目录已存在，先比较版本。

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

## 验收要看什么

| 现场情况 | 期望看见的行为 |
| --- | --- |
| 代理正常 | 真实应用的新请求经批准的出口成功，独立的直连对照也能工作。 |
| VPS 上游失联，但本机代理仍监听 | 所有能承接受保护流量的上游确实不可用；受保护请求在故障窗口内无法完成，不得切到直连或未经认可的备用节点。 |
| 管理器、核心和 TUN 全部退出 | 同一应用发出的新请求失败；同时查系统是否拦截了该应用的直连尝试。 |
| 仅 TUN 停止，本机代理仍可用 | 显式代理路径可以继续工作。绕过它去物理网络的尝试应被阻止。 |

故障中排队、恢复后才收到回复，须按时间分开记录。CLI、桌面应用、浏览器和 DNS 解析器各自取证。查看 [技能入口](skills/ai-agent-proxy-guard/SKILL.md)。

分流方法参考 [AgentRoute](https://github.com/ryuu-restart/agent-route)，本仓库不分发其规则名单。原创技能和采样器以 [MIT 许可证](LICENSE)开放使用。
