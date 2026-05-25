#!/usr/bin/env python3
import socket
import select
import sys
import termios
import tty

# ===== 配置区域 =====
# 替换为你的服务器 Tailscale IP（通过 tailscale status 查看）
HOST = '100.0.0.0'  # 示例 IP，请修改为实际 IP
PORT = 9999
# ===================

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