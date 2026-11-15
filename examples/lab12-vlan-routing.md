# 示例 2：实验12 VLAN 间路由（每个 VLAN 一个物理接口，不用单臂路由）

## 拓扑与连线

| 设备 | 型号 | 说明 |
|---|---|---|
| S1 | 2950-24 | VLAN2 / VLAN3 接入 |
| R1 | 2621XM | 两个物理口分别作两个 VLAN 的网关 |
| HOST A | PC-PT | 192.168.0.2/24，网关 192.168.0.1（VLAN2） |
| HOST B | PC-PT | 192.168.0.3/24，网关 192.168.0.1（VLAN2） |
| HOST C | PC-PT | 192.168.1.2/24，网关 192.168.1.1（VLAN3） |

连线（全部直通）：

- HOST A → S1 f0/1
- HOST B → S1 f0/2
- HOST C → S1 f0/16
- S1 f0/7 → R1 Fa0/0（VLAN2 网关口）
- S1 f0/8 → R1 Fa0/1（VLAN3 网关口）

## S1

```
enable
configure terminal
hostname S1
vlan 2
 name vlan2
 exit
vlan 3
 name vlan3
 exit
interface range FastEthernet0/1-8
 switchport mode access
 switchport access vlan 2
 exit
interface range FastEthernet0/9-16
 switchport mode access
 switchport access vlan 3
 exit
interface FastEthernet0/8
 switchport access vlan 3
 exit
end
write
```

> f0/8 是 R1 的第二个网关口，必须从 VLAN2 改到 VLAN3；做完用 `show interfaces status` 核对每个 connected 端口的 VLAN 是否正确。

## R1

```
enable
configure terminal
hostname R1
interface FastEthernet0/0
 ip address 192.168.0.1 255.255.255.0
 no shutdown
 exit
interface FastEthernet0/1
 ip address 192.168.1.1 255.255.255.0
 no shutdown
 exit
end
write
```

## PC（Desktop → IP Configuration）

| 主机 | IP | 掩码 | 网关 |
|---|---|---|---|
| HOST A | 192.168.0.2 | 255.255.255.0 | 192.168.0.1 |
| HOST B | 192.168.0.3 | 255.255.255.0 | 192.168.0.1 |
| HOST C | 192.168.1.2 | 255.255.255.0 | 192.168.1.1 |

## 验证

```
S1#show vlan brief
2    vlan2   active   Fa0/1 ... Fa0/7
3    vlan3   active   Fa0/8 ... Fa0/16

S1#show interfaces status
Fa0/7  connected  2     ← 通往 R1 Fa0/0
Fa0/8  connected  3     ← 通往 R1 Fa0/1

HOST A: ping 192.168.0.3    → TTL=128（同 VLAN，不经路由器）
HOST A: ping 192.168.1.2    → TTL=127（跨 VLAN，经 1 跳）
HOST A: tracert 192.168.1.2 → 1: 192.168.0.1 → 2: 192.168.1.2
```

## 排错顺序（跨 VLAN ping 不通时）

1. `show interfaces status`：两个网关口是否 connected，VLAN 是否分别为 2 / 3；
2. `show cdp neighbors`（在 R1 上）：确认 Fa0/0、Fa0/1 各自接到交换机哪个口；
3. `show ip interface brief`（在 R1 上）：两个接口是否 up/up、IP 是否在对应网段；
4. 主机 IP/网关是否填对（注意掩码先填、再 IP、再网关）；
5. 仍不通时再看是否少了一根线——两根平行线在画布上会重叠，肉眼看不出缺线。
