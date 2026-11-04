# 分流、DNS 与 WebRTC

在同一次请求中，域名解析、普通 HTTPS 和实时媒体可能各走一条路。为每条路分别写出预期出口、证据来源和故障时的行为。

## 分流的作用域与顺序

把受保护流量接入一个只绑定回环、仅供该应用使用的入站，并把该入站整体送往批准的上游。这能覆盖代理核心收到的 IP 字面量和未来新增域名。共享入站可按**实际可取得**的进程身份匹配，应用端另有系统阻断。单靠域名补充表时，将保护范围明确限定在已列目标。共享浏览器的网络进程可能服务多个标签页；需要按程序隔离时使用可独立识别的宿主或运行环境，单开一个标签页无法提供这种隔离。

| 判定层 | 处理方式 |
| --- | --- |
| 核心建立传输 | 只给核心连接已批准节点和解析其名称所需的最小例外；避免节点连接又进入自己的隧道。 |
| 受保护入站、进程和服务后缀 | 送固定出站或明确拒绝。检查代理组及嵌套组的实际成员，禁用失败转直连、系统代理自动发现和针对受保护目标的旁路。拒绝某目标是安全失败。 |
| 普通流量 | 保留用户例外、内网、拒绝、代理域名、直连域名和地区 IP 兜底。域名判定优先于地区 IP，默认未知公网流量按约定处理。任何普通直连例外都不得越过上一层。 |

在 Mihomo 的规则模式中，如果当前核心支持 `IN-NAME`，且已建好相应专用入站和固定代理组，可以用下面的**前置片段**表达策略。名称均为示例。核心先识别并处理自己的节点传输，下面的业务规则不为应用放行任何节点直连。

```yaml
rules:
  - IN-NAME,protected-in,PINNED-EGRESS
  # Append the existing general rules and their single final MATCH here.
```

不要把这个片段当完整配置导入。核验监听者与绑定地址、规则首命中、组内只有批准的节点，以及订阅刷新后 GUI 实际生成的配置。没有专用入站时，若平台能取得专用进程的真实身份，可改用 `PROCESS-NAME,agent-example.exe,PINNED-EGRESS` 并验证命中。单独的 `DOMAIN-SUFFIX,service.example,PINNED-EGRESS` 会改变所有使用该核心的程序访问同后缀的路径，仅在用户需要这种全局行为时添加。

sing-box 使用对应版本的入站标签、路由动作和规则集；Xray 前端可能另外生成 TUN 核心配置，两处都要检查。精确域名和后缀的语义不同。对 FakeIP 先还原映射，避免合成地址被当作内网地址放行。检验普通内网、直连、代理、拒绝和受保护目标各一个样本，再检验受保护入站访问 IP 或未知名的样本。[Mihomo 规则](https://wiki.metacubex.one/config/rules/) · [sing-box 路由动作](https://sing-box.sagernet.org/configuration/route/rule_action/)

AgentRoute 发布 `private`、`reject`、`proxy`、`direct`、`cn-ip` 五类通用资源，按核心选择格式。需要可复现更新时，固定同一 release 提交，核对索引、清单摘要及非空资源，校验后切换本地代际指针。刷新失败保留上一份已验证资源，首次没有好版本时让受保护路径保持关闭。客户端还要证明确实装载了该代规则。仓库不包含上游名单或订阅。[所审阅的 AgentRoute 版本](https://github.com/ryuu-restart/agent-route/tree/39c5ce06f86c08347e31a4decdf1bde58d9dc881) · [客户端适配](https://github.com/ryuu-restart/agent-route/blob/39c5ce06f86c08347e31a4decdf1bde58d9dc881/docs/CLIENTS.md) · [同步与回退实现](https://github.com/ryuu-restart/agent-route/blob/39c5ce06f86c08347e31a4decdf1bde58d9dc881/scripts/sync_rules.py)

## DNS 要追到解析器的出站

| 查询 | 预期处理 | 取证要点 |
| --- | --- | --- |
| 受保护服务、受保护上下文中的未知公网名 | 由专用代理远端解析，或由只经批准出口访问的可信加密解析器解析；失败也不交给系统公共备用。 | 从目标应用制造带随机标签的未缓存查询，关联核心 DNS 日志、解析器实际连接和规则命中。HTTP CONNECT / SOCKS 的域名交给中继；使用 SOCKS 时确认客户端确实启用了远端解析。 |
| 节点名 | 只给引导解析器必要的例外，限定发起者和用途。 | 在隧道建立前能解析节点，受保护业务名不会被送到引导解析器。固定 IP 的受信任节点可免此步。 |
| 普通国内域名及独立例外 | 维持约定的可信解析出口，核查第二次解析和备用解析。 | 查系统服务、浏览器独立 DoH、DHCP、并发与 fallback。核对 A/AAAA 及使用中的 TCP/UDP 53、DoT、DoH/HTTP3。 |
| 真实使用的内网名称 | 经已核实的内网 DNS 或 mDNS。 | 回环 stub 还要查下一跳；用自有合成测试名。无法查到下一跳则注明缺口。 |

很多应用把 DNS 委托给系统服务，按应用拦出站可能拦不到这些查询。使用专用代理的远端解析、可按域名控制且无直连备用的本地解析入口，或把应用和 DNS 一起隔离。若要求保护**所有**该应用发起的查询，包括未知域名，而共享解析器无法识别来源，就需要独立解析上下文。解析器日志中只有名称、DoH 已加密、HTTP 出口正确、A/AAAA 返回 FakeIP、第三方页面报出的公共递归解析器，都不足以证明查询经过指定出口。可以用自有权威域名的查询日志辅助，递归服务器地址也不能单独还原客户端到递归服务器的路径。[Mihomo DNS](https://wiki.metacubex.one/config/dns/) · [AgentRoute 解析与浏览器验收](https://github.com/ryuu-restart/agent-route/blob/39c5ce06f86c08347e31a4decdf1bde58d9dc881/docs/DNS-WEBRTC.md)

故障时在同一受控域下换一个全新标签，同时观察本地解析链和物理出口。保留局域网名称与业务凭据的隐私。故障中的缓存命中可以正常返回；应继续用未缓存样本判断是否存在查询外发。

## WebRTC 与 IPv6

1. 在**实际使用的浏览器配置档或内嵌运行时**确认 HTTPS 的批准出口。只在用户认可的 STUN/TURN 端点测试；错误配置时，该端点可能看到本地公网地址。优先使用自托管的测试页。使用 Trickle ICE 示例时，开始收集前移除所有预填或从浏览器存储恢复的未批准服务器，确认清单只剩认可的目标。不要把长期 TURN 凭据填入公共演示页。保留代理和系统防护，先在允许路径上确认端点本身可用。[示例页的服务器清单实现](https://github.com/webrtc/samples/blob/gh-pages/src/content/peerconnection/trickle-ice/js/main.js)
2. 收集 ICE 候选，条件允许时一起检查实际选中的候选对、核心和物理接口流量。`host` 可为私网地址或 mDNS 名称；`srflx` 是 STUN 观察到的映射；`relay` 是 TURN 中继地址，也要核查到中继的连接是否绕路。比较批准的出口**集合**，兼顾 IPv4 和 IPv6，记录是否暴露了未经批准的公网地址。只有内网 host 候选时，另行说明对局域网地址的披露范围。
3. 对支持的浏览器，可核对 `webRTCIPHandlingPolicy` 的 `disable_non_proxied_udp` 设置及实际生效状态。桌面内嵌引擎需单独验证。需要音视频时复测实际通话；无候选、没有摄像头、只装了扩展或关闭了 UDP，均不能独立证明出口正确。[浏览器隐私接口](https://developer.chrome.com/docs/extensions/reference/api/privacy) · [WebRTC 地址处理规范](https://www.rfc-editor.org/rfc/rfc8828) · [Trickle ICE 测试页](https://webrtc.github.io/samples/src/content/peerconnection/trickle-ice/)
4. 核对物理网卡的公网 IPv6、默认路由、隧道 IPv6 路由、解析器和直连阻断。分别证明应用在批准路径能否走 IPv6，以及它能否绕开该路径直出。代理替客户端访问 IPv6 网站只能佐证代理一侧。隧道只支持 IPv4 时，在受保护身份或隔离边界显式阻断 IPv6 外发；保留配置所需的本地链路能力。没有可用 IPv6 对照时，未来有 IPv6 的网络仍为未验证。
