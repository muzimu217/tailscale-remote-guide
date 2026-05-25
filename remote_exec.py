#!/usr/bin/env python3
import socket

HOST = '100.78.139.20'
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

# 使用示例
if __name__ == '__main__':
    import sys
    cmd = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else 'pwd'
    print(exec_remote(cmd), end='')