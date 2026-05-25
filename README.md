# Tailscale 远程服务器使用指南

## 概述

本指南介绍两种基于 Tailscale 的远程服务器管理方案：

- **方案一：SSH 免密登录** - 适用于有 SSH 权限的服务器，使用标准 SSH 配置
- **方案二：Python TCP Shell** - 适用于无 SSH 权限或 SSH 端口被限制的服务器，使用 Python 脚本实现

## 前置条件

1. **Tailscale 已安装并登录**
   ```bash
   # 安装
   curl -fsSL https://tailscale.com/install.sh | sh
   
   # 登录
   sudo tailscale up
   ```

2. **Python 3.x**（仅方案二需要）

## 方案一：SSH 免密登录

### 配置步骤

#### 1. 生成 SSH 密钥（如果没有）
```bash
ssh-keygen -t ed25519 -f ~/.ssh/my_server_key -N ""
```

#### 2. 添加公钥到服务器
```bash
# 查看公钥
cat ~/.ssh/my_server_key.pub

# 在服务器上执行：
mkdir -p ~/.ssh
echo "你的公钥内容" >> ~/.ssh/authorized_keys
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

#### 3. 添加主机密钥
```bash
ssh-keyscan <服务器IP> >> ~/.ssh/known_hosts
```

#### 4. 测试连接
```bash
ssh -i ~/.ssh/my_server_key user@<服务器IP>
```

### 使用方法

#### 连接
```bash
ssh user@<服务器IP>
```

#### 执行命令
```bash
ssh user@<服务器IP> "ls -la"
ssh user@<服务器IP> "df -h && free -h"
```

#### 文件传输
```bash
# 上传
scp local.txt user@<服务器IP>:/tmp/

# 下载
scp user@<服务器IP>:/var/log/*.log ~/logs/

# 目录
scp -r local_dir user@<服务器IP>:/home/user/
```

#### 端口转发
```bash
# 本地端口转发
ssh -L 8080:localhost:80 user@<服务器IP>

# 远程端口转发
ssh -R 8080:localhost:8080 user@<服务器IP>

# SOCKS 代理
ssh -D 1080 user@<服务器IP>
```

---

## 方案二：Python TCP Shell（无 SSH 权限）

适用于无 root 权限、无法使用 SSH 的服务器。

### 脚本：remote_exec.py（单次命令执行）

```python
#!/usr/bin/env python3
import socket

HOST = '服务器IP'
PORT = 9999

def exec_remote(cmd):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((HOST, PORT))
    s.recv(1024)  # 接收提示符
    s.send(f'{cmd}\n'.encode())
    result = s.recv(32768).decode()
    s.close()
    # 移除末尾提示符
    return result.replace('>>> ', '')

if __name__ == '__main__':
    import sys
    cmd = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else 'pwd'
    print(exec_remote(cmd), end='')
```

### 脚本：remote_shell_interactive.py（交互式 Shell）

```python
#!/usr/bin/env python3
import socket
import select
import sys
import termios
import tty

HOST = '服务器IP'
PORT = 9999

def interactive_shell():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((HOST, PORT))
    s.recv(1024)  # 接收初始提示
    
    # 设置终端为原始模式
    old_settings = termios.tcgetattr(sys.stdin)
    try:
        tty.setraw(sys.stdin.fileno())
        
        while True:
            # 使用 select 检查可读的文件描述符
            rlist, _, _ = select.select([s, sys.stdin], [], [])
            
            for sock in rlist:
                if sock == s:
                    # 接收远程数据
                    data = s.recv(4096)
                    if not data:
                        print('\n连接断开')
                        return
                    sys.stdout.write(data.decode(errors='ignore'))
                    sys.stdout.flush()
                elif sock == sys.stdin:
                    # 发送本地输入
                    data = sys.stdin.read(1)
                    if data == '\x04':  # Ctrl+D 退出
                        return
                    s.send(data.encode())
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        s.close()

if __name__ == '__main__':
    print(f'连接到 {HOST}:{PORT}')
    print('按 Ctrl+D 退出')
    interactive_shell()
```

### 服务器端配置

#### 1. 启动交互式 Shell 服务

```bash
nohup python3 << 'PYEOF' > /tmp/shell.log 2>&1 &
import socket
import subprocess
import os
import threading

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(('0.0.0.0', 9999))
server.listen(1)
print('Interactive shell server ready', flush=True)

conn, addr = server.accept()
print(f'Connected from {addr}', flush=True)

conn.send(b'Interactive shell ready. Press Ctrl+C to exit.\n')

# 创建 PTY
import pty
master_fd, slave_fd = pty.openpty()

# 启动 shell
shell = subprocess.Popen(
    ['/bin/bash'],
    stdin=slave_fd,
    stdout=slave_fd,
    stderr=slave_fd,
    preexec_fn=os.setsid
)

# 读取 PTY 输出并发送到客户端
def read_pty():
    while True:
        try:
            data = os.read(master_fd, 1024)
            if not data:
                break
            conn.sendall(data)
        except:
            break

thread = threading.Thread(target=read_pty)
thread.daemon = True
thread.start()

# 读取客户端输入并发送到 PTY
try:
    while True:
        data = conn.recv(1024)
        if not data:
            break
        os.write(master_fd, data)
except:
    pass

# 清理
os.close(master_fd)
os.close(slave_fd)
shell.terminate()
conn.close()
server.close()
PYEOF

# 验证
sleep 2
netstat -tlnp | grep 9999
```

#### 2. 启动单命令执行服务（可选）

```bash
nohup python3 << 'PYEOF' > /tmp/shell.log 2>&1 &
import socket
import subprocess

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(('0.0.0.0', 9999))
server.listen(1)
print('Server ready', flush=True)

while True:
    try:
        conn, addr = server.accept()
        conn.send(b'>>> ')
        
        # 接收命令
        data = conn.recv(1024)
        if not data:
            conn.close()
            continue
        
        cmd = data.decode().strip()
        print(f'Exec: {cmd}', flush=True)
        
        # 执行命令
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        output = result.stdout + result.stderr
        
        # 发送结果
        conn.send(output.encode())
        conn.send(b'\n>>> ')
        conn.close()
    except Exception as e:
        print(f'Error: {e}', flush=True)
        conn.close()
server.close()
PYEOF
```

### 使用方法

#### 单次命令
```bash
python3 remote_exec.py "ls -la"
python3 remote_exec.py "df -h"
python3 remote_exec.py "ps aux"
```

#### 交互式 Shell
```bash
python3 remote_shell_interactive.py
```

#### 快捷命令
```bash
# 添加到 ~/.zshrc 或 ~/.bashrc
echo 'alias remote-cmd="python3 /path/to/remote_exec.py"' >> ~/.zshrc
echo 'alias remote-shell="python3 /path/to/remote_shell_interactive.py"' >> ~/.zshrc
source ~/.zshrc

# 使用
remote-cmd "ls -la"
remote-shell
```

---

## Tailscale 管理

### 查看设备
```bash
tailscale status
```

### 测试连通性
```bash
ping <服务器IP>
nc -zv <服务器IP> <端口>
```

### 故障排除
```bash
# 重启服务
sudo systemctl restart tailscaled

# 查看日志
sudo journalctl -u tailscaled -f

# 重新连接
tailscale down
tailscale up
```

---

## 常用命令示例

### 系统信息
```bash
# SSH
ssh user@<IP> "uname -a"
ssh user@<IP> "df -h && free -h"

# Python Shell
python3 remote_exec.py "uname -a"
python3 remote_exec.py "df -h && free -h"
```

### 进程管理
```bash
# 查看进程
python3 remote_exec.py "ps aux | grep python"

# 杀死进程
python3 remote_exec.py "kill <PID>"
```

### 日志查看
```bash
# 查看日志
python3 remote_exec.py "tail -f /var/log/syslog"

# 查看错误
python3 remote_exec.py "journalctl -xe"
```

---

## 安全建议

1. **最小权限原则**
   - 使用非 root 用户
   - 限制命令执行范围

2. **网络安全**
   - 定期检查 Tailscale ACL
   - 启用两步验证

3. **数据安全**
   - 定期备份重要数据
   - 使用加密传输

4. **日志监控**
   - 监控连接日志
   - 异常行为告警

---

## 故障排除

### 无法连接
```bash
# 检查 Tailscale 状态
tailscale status

# 检查网络
ping <IP>

# 检查端口
nc -zv <IP> <PORT>
```

### 服务重启
```bash
# 停止旧服务
kill $(pgrep -f "python3.*9999")

# 启动新服务（参考上面的配置步骤）
```

### 权限问题
```bash
# 检查用户权限
id

# 检查文件权限
ls -la
```

---

## 进阶用法

### 多服务器管理
```bash
# 创建配置文件
cat > servers.conf << EOF
dev1=100.112.43.52:developer
dev2=100.78.139.20:aistudio
EOF

# 批量执行
for server in $(cat servers.conf); do
  IP=$(echo $server | cut -d: -f1)
  USER=$(echo $server | cut -d: -f2)
  ssh $USER@$IP "uptime"
done
```

### 自动化脚本
```bash
#!/bin/bash
# 自动化备份

for server in dev1 dev2; do
  echo "备份 $server..."
  # 执行备份操作
done
```

---

## 总结

- **SSH 方案**：适合有完整权限的服务器，功能强大
- **Python Shell 方案**：适合受限环境，绕过 SSH 限制
- **Tailscale**：提供安全、稳定的网络连接

根据实际环境选择合适的方案。

---

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！