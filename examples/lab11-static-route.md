# 示例 1：实验11 静态路由（两台路由器 + 串口 + 交换机 + 两台 PC）

## 拓扑与连线

| 设备 | 型号 | 说明 |
|---|---|---|
| R1 | 2621XM + WIC-2T | 左侧路由器，DCE 端 |
| R2 | 2621XM + WIC-2T | 右侧路由器，DTE 端 |
| S1 | 2950-24 | 接 PC0 与 R1 |
| PC0 | PC-PT | 192.168.1.10/24，网关 192.168.1.1 |
| PC1 | PC-PT | 192.168.3.10/24，网关 192.168.3.1 |

连线（直通用 8100、交叉用 8101、串口用 DCE 线）：

- PC0 Fa0 → S1 f0/1
- S1 f0/24 → R1 Fa0/0
- R1 Serial0/0 → R2 Serial0/0（**Serial DCE**，R1 为 DCE）
- R2 Fa0/0 → PC1 Fa0（**交叉线**）

## R1

```
enable
configure terminal
hostname R1
interface FastEthernet0/0
 ip address 192.168.1.1 255.255.255.0
 no shutdown
 exit
interface Serial0/0
 ip address 192.168.2.1 255.255.255.0
 clock rate 64000
 no shutdown
 exit
ip route 192.168.3.0 255.255.255.0 192.168.2.2
end
write
```

## R2

```
enable
configure terminal
hostname R2
interface FastEthernet0/0
 ip address 192.168.3.1 255.255.255.0
 no shutdown
 exit
interface Serial0/0
 ip address 192.168.2.2 255.255.255.0
 no shutdown
 exit
ip route 192.168.1.0 255.255.255.0 192.168.2.1
end
write
```

## PC（Desktop → IP Configuration）

| PC | IP | 掩码 | 网关 |
|---|---|---|---|
| PC0 | 192.168.1.10 | 255.255.255.0 | 192.168.1.1 |
| PC1 | 192.168.3.10 | 255.255.255.0 | 192.168.3.1 |

## 验证

```
R1#show ip route
C    192.168.1.0/24 is directly connected, FastEthernet0/0
C    192.168.2.0/24 is directly connected, Serial0/0
S    192.168.3.0/24 [1/0] via 192.168.2.2

R1#show ip interface brief
FastEthernet0/0   192.168.1.1   YES manual up   up
Serial0/0         192.168.2.1   YES manual up   up

PC1: ping 192.168.1.10      → 首包超时，其后 Reply，TTL=126
PC1: tracert 192.168.1.10   → 3.1 → 2.1 → 1.10
```

## 三种路由写法（替换下一跳写法时用）

```
! 出接口写法
configure terminal
no ip route 192.168.3.0 255.255.255.0 192.168.2.2
ip route 192.168.3.0 255.255.255.0 Serial0/0
end
! 路由表显示：S 192.168.3.0/24 is directly connected, Serial0/0

! 默认路由
configure terminal
no ip route 192.168.3.0 255.255.255.0 Serial0/0
ip route 0.0.0.0 0.0.0.0 192.168.2.2
end
! 路由表显示：Gateway of last resort is 192.168.2.2 + S* 0.0.0.0/0

! 汇总路由：R2 建 4 个 Loopback，R1 用 /22 汇总
! R2:
configure terminal
interface Loopback0
 ip address 192.168.4.1 255.255.255.0
interface Loopback1
 ip address 192.168.5.1 255.255.255.0
interface Loopback2
 ip address 192.168.6.1 255.255.255.0
interface Loopback3
 ip address 192.168.7.1 255.255.255.0
end
! R1:
configure terminal
no ip route 0.0.0.0 0.0.0.0 192.168.2.2
ip route 192.168.4.0 255.255.252.0 192.168.2.2
end
! 路由表显示：S 192.168.4.0/22 [1/0] via 192.168.2.2
```

做完演示记得把 R1 恢复成下一跳写法并 `write`。
