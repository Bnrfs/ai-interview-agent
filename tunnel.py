"""启动隧道暴露 8000 端口"""
import time
from pyngrok import ngrok, conf

conf.get_default().region = "ap"

try:
    tunnel = ngrok.connect(8000, "http")
    url = tunnel.public_url
    print(f"PUBLIC_URL={url}")
    # 写入文件供读取
    with open("/tmp/public_url.txt", "w") as f:
        f.write(url)
    # 保持连接
    while True:
        time.sleep(60)
except Exception as e:
    print(f"ERROR: {e}")
