# 系统级保护与 Windows 示例

先选能够区分受保护应用和代理核心的边界。规则必须在代理尚未启动、已退出和重新连接的间隙都生效。若漏出的那一次请求也不能接受，在边界就绪前保持目标关闭，在隔离环境验证后再投用。

## Windows：先确定谁在联网

定位一次真实请求的主进程、网络服务子进程和 CLI，记录 PID、启动时间、签名、程序路径、包身份，以及实际连接的监听者。单用 PID 容易认错已重用的进程。桌面与 CLI 分开检查；一个进程的拦截事件不能算在另一个进程名下。桌面宿主、更新器、插件和共享运行时也可能代为发起连接。

先只读查看将要依赖的能力，并在本地保存输出。域策略可能压过本地配置。检查防火墙服务、所有网络配置文件的有效状态和现有规则。

```powershell
Get-NetFirewallProfile -PolicyStore ActiveStore |
    Select-Object Name, Enabled, DefaultOutboundAction, AllowLocalFirewallRules
Get-NetAdapter | Select-Object Name, Status, InterfaceDescription
Get-NetRoute | Where-Object DestinationPrefix -in '0.0.0.0/0','::/0'
(Get-Command New-NetFirewallRule).Parameters.Keys |
    Where-Object { $_ -in 'Program','Package','PolicyAppId','InterfaceType' }
```

### 架构 A：应用显式使用可信回环代理

适用于应用能把公网业务交给本机 HTTP/SOCKS 入口的场景。给该入口单独的入站标签及固定上游，确认只监听回环；应用自身不需要直接连接局域网或公网。代理进程必须有独立身份。即使客户端改用直连，其到非回环目的地的连接也应被系统阻断。

下面的 PowerShell **仅预览**一条针对单个原生可执行文件的规则。先把 `$agentExe` 换成已核实的专用联网程序绝对路径。范围覆盖非回环的可路由 IPv4/IPv6 目的地，所有接口、协议、端口和网络配置文件；因此该程序也无法直接访问内网服务。需要这种访问时先重新设计边界。

```powershell
$agentExe = Read-Host 'Absolute path of the dedicated network executable'
$agentFile = Get-Item -LiteralPath $agentExe -ErrorAction Stop
if ($agentFile.PSIsContainer -or $agentFile.Extension -ne '.exe') {
    throw 'Expected a dedicated executable'
}
Get-AuthenticodeSignature -LiteralPath $agentFile.FullName |
    Select-Object Status, SignerCertificate
$ruleName = 'AgentProxyGuard-' + [guid]::NewGuid().ToString('N')
$rule = @{
    Name          = $ruleName
    DisplayName   = $ruleName
    PolicyStore   = 'PersistentStore'
    Direction     = 'Outbound'
    Action        = 'Block'
    Profile       = 'Any'
    Protocol      = 'Any'
    Program       = $agentFile.FullName
    RemoteAddress = @(
        '0.0.0.0-126.255.255.255'
        '128.0.0.0-255.255.255.255'
        '::2-ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff'
    )
}
$rule | Format-List
New-NetFirewallRule @rule -WhatIf
```

- 保存每个拟新增的唯一 `Name`、目标身份、参数和恢复命令。应用前查有没有等效规则以及本轮部分成功留下的规则，复用已核对的项目；不要重复运行整段生成新名称。已经获准、身份和恢复路径已核实后，在正常的管理员会话按已保存参数执行 `New-NetFirewallRule @rule -ErrorAction Stop`。任一目标失败，保持目标应用关闭，按本轮清单恢复或补齐。
- 分别读回 `Get-NetFirewallRule -PolicyStore PersistentStore -Name $ruleName` 和 `Get-NetFirewallRule -PolicyStore ActiveStore -Name $ruleName`，把有效规则分别送入 `Get-NetFirewallApplicationFilter` 和 `Get-NetFirewallAddressFilter`，核对身份、两个地址族和阻断范围；再做正负对照。预览、规则存在、远端显示回环都不能代替阻断实测。
- 回环本身是信任边界。此规则允许处于回环范围内的其他服务。核实所有可被应用调用的转发器都符合策略，并检查端口监听者身份；本机存在可绕路的转发器或不能信任的同机进程时，改用只暴露指定中继的隔离环境。共享系统 DNS 的外发也需另行封住。
- 撤销时先暂停受保护应用，凭已保存的确切名称和程序身份核对规则，再执行 `Remove-NetFirewallRule -PolicyStore PersistentStore -Name $ruleName`；逐项确认已移除。修改前已有的规则、组织策略和防火墙全库不属于这次撤销。恢复到缺少系统保护的旧配置后，目标须保持关闭，直到用户选定可接受的运行方式。

Windows 显式阻止优先于与之冲突的允许规则。若对同一程序既设全目标 Block 又设回环 Allow，不能指望后者覆盖前者；应让地址或接口条件互不重叠。每个实际联网身份都要覆盖。[Windows 防火墙规则优先级](https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/rules) · [New-NetFirewallRule 参数](https://learn.microsoft.com/en-us/powershell/module/netsecurity/new-netfirewallrule)

### 架构 B：应用由 TUN 透明接管

此时应用看到的目的地可能是业务公网地址，架构 A 的规则可能连正常隧道也一并阻断。需要按接口或隔离环境区分应用的隧道出口与物理直连。枚举以太网、Wi-Fi、移动热点、远程访问和虚拟网卡的**实际路由与分类**；不能简单把所有虚拟网卡都当作安全出口。覆盖新网卡、切网、启动先后和双栈。不能可靠区分时，转用显式中继或隔离边界，再重新验收。

版本化安装目录会使 `-Program` 路径规则在升级后失效。受支持的 Windows 版本可评估稳定的包身份，以及按签名发布者**加具体产品/文件身份**的 App Control 标签策略和防火墙 `PolicyAppId`。只给特定程序打标签，避免标记所有同厂商或共享解释器。查新启动的真实主进程和联网子进程令牌、有效的 WFP 过滤器和实际丢弃事件。靠单一旧路径、仅部署了标签策略、只检查进程名，都不足以覆盖升级。自动更新后若无法确认新架构继续受约束，应先暂停受保护工作负载。[AppId 标签策略](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/appidtagging/design-create-appid-tagging-policies)

多个核心并行时，某些驱动在 WFP 自有子层为核心放行。普通按节点 IP 添加的一条临时 Block，可能只切断其中一个核心。证明每一条实际上游都已失效后才开始计时；必要时改在隔离网络的上游一侧注入故障。[WFP 过滤器仲裁](https://learn.microsoft.com/en-us/windows/win32/fwp/filter-arbitration)

## 其他平台怎样选边界

| 环境 | 可采用的边界 | 必须核实 |
| --- | --- | --- |
| Linux、容器或子系统 | 让专用用户或网络命名空间只能接触批准的中继，核心位于另一边界；在受保护侧使用默认拒绝出站。 | 宿主和来宾分别查路由、IPv6、DNS、共享 socket 与默认网关。阻断共享解释器可能影响其他应用。 |
| macOS | 使用能在隧道离开后继续执行的系统网络过滤或应用隔离能力；Web 代理或 PAC 自身不足以约束原生进程。 | 核实实际版本、应用身份、启动和切网行为。规则只能跟随代理客户端存活时，完整退出记未验证或失败。 |
| Android | 选择支持系统始终开启 VPN 和「阻止不使用 VPN 的连接」的组合，核对分应用清单和设备管理限制。 | 受保护包没有被排除；断开、重启、Wi-Fi/移动网切换均单测。未知 UID 不能代替真实应用；系统锁定可能影响其他应用。 |
| iOS / iPadOS | 区分按需重连、受管的始终开启 VPN 及设备实际支持的能力。 | 没有持久强制边界时只能报告已测路由行为。手机节点订阅能导入、桌面规则通过，均不能证明真机阻断。 |
