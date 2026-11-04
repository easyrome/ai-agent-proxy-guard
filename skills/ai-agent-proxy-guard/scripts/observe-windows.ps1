#requires -Version 5.1
<#
.SYNOPSIS
Sample local socket tables for explicitly selected process instances.
.DESCRIPTION
Read-only. Writes JSON to stdout, without remote IPs or executable paths.
Exit 0 means sampling finished, not that egress is safe. Exit 2 means incomplete.
Pass every verified network worker PID; children are not discovered automatically.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateRange(1, 2147483647)]
    [int[]] $ProcessId,

    [Parameter(Mandatory)]
    [ValidateRange(1, 65535)]
    [int[]] $ProxyPort,

    [ValidateRange(1, 120)]
    [int] $Samples = 5,

    [ValidateRange(0, 60000)]
    [int] $IntervalMs = 1000
)

$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'Windows socket tables are required.'
}

function Get-StartTicks([int] $Id) {
    try {
        return (Get-Process -Id $Id -ErrorAction Stop).StartTime.ToUniversalTime().Ticks
    }
    catch {
        return $null
    }
}

function Get-PeerCategory($Connection) {
    [Net.IPAddress] $address = $null
    if (-not [Net.IPAddress]::TryParse([string]$Connection.RemoteAddress, [ref]$address)) {
        return 'unknown/unclassified'
    }
    if ($address.IsIPv4MappedToIPv6) {
        $address = $address.MapToIPv4()
    }
    $family = 'IPv6'
    if ($address.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork) {
        $family = 'IPv4'
    }
    if (-not [Net.IPAddress]::IsLoopback($address)) { return "$family/non_loopback" }
    $standardLoopback = ($address.Equals([Net.IPAddress]::Loopback) -or
                         $address.Equals([Net.IPAddress]::IPv6Loopback))
    if ($standardLoopback -and $ProxyPort -contains [int]$Connection.RemotePort) {
        return "$family/expected_loopback_port"
    }
    return "$family/other_loopback"
}

$ids = @($ProcessId | Sort-Object -Unique)
$originalStart = @{}
foreach ($id in $ids) { $originalStart[$id] = Get-StartTicks $id }
$rows = New-Object 'System.Collections.Generic.List[object]'
$incomplete = $false
for ($i = 1; $i -le $Samples; $i++) {
    $begin = [DateTime]::UtcNow.ToString('o')
    $before = @{}
    foreach ($id in $ids) { $before[$id] = Get-StartTicks $id }
    $tcp = $null
    $udp = $null
    try { $tcp = @(Get-NetTCPConnection -ErrorAction Stop | Where-Object { $ids -contains $_.OwningProcess }) }
    catch { $incomplete = $true }
    try { $udp = @(Get-NetUDPEndpoint -ErrorAction Stop | Where-Object { $ids -contains $_.OwningProcess }) }
    catch { $incomplete = $true }

    foreach ($id in $ids) {
        $after = Get-StartTicks $id
        $stable = ($null -ne $originalStart[$id] -and $before[$id] -eq $originalStart[$id] -and
                   $after -eq $originalStart[$id])
        $tcpCounts = $null
        $udpBindings = $null
        if (-not $stable) { $incomplete = $true }
        if ($stable -and $null -ne $tcp) {
            $tcpCounts = [ordered]@{}
            foreach ($connection in $tcp) {
                if ($connection.OwningProcess -ne $id -or $connection.RemotePort -eq 0) { continue }
                $key = "$(Get-PeerCategory $connection)/$($connection.State)"
                $tcpCounts[$key] = 1 + [int]$tcpCounts[$key]
            }
        }
        if ($stable -and $null -ne $udp) {
            $udpBindings = @($udp | Where-Object OwningProcess -eq $id).Count
        }
        $rows.Add([ordered]@{
            sample = $i
            began_utc = $begin
            ended_utc = [DateTime]::UtcNow.ToString('o')
            pid = $id
            initial_start_ticks_utc = [string]$originalStart[$id]
            same_instance = $stable
            tcp_peer_and_state_counts = $tcpCounts
            udp_local_bindings = $udpBindings
        })
    }
    if ($i -lt $Samples -and $IntervalMs -gt 0) { Start-Sleep -Milliseconds $IntervalMs }
}
$status = 'sampled'
if ($incomplete) { $status = 'incomplete' }
[ordered]@{
    status = $status
    evidence = 'socket_snapshots_only'
    samples = $rows.ToArray()
} | ConvertTo-Json -Depth 7
if ($incomplete) { exit 2 }
