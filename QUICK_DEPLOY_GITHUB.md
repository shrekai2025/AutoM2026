# AutoM2026 快速部署指南（GitHub 方式）

## 前提条件

- Ubuntu 20.04+ 服务器
- 至少 2GB 内存，1 核 CPU
- 有 GitHub 访问权限

---

## 一、推送代码到 GitHub

### 1. 检查敏感信息

确保 `.env` 文件已在 `.gitignore` 中（已配置✅）

```bash
# 在本地检查
cd /Users/davidzhang/Documents/AutoMoney/AutoM2026
git status

# 确保 .env 不在待提交列表中
```

### 2. 提交并推送代码

```bash
# 添加新文件
git add .env.example UBUNTU_DEPLOY_GUIDE.md

# 提交
git commit -m "Add deployment guide and env template"

# 推送到 GitHub
git push origin main
```

### 3. 设置仓库为公开（可选）

如果仓库是私有的，可以在 GitHub 上设置为公开：
- 进入仓库页面
- Settings → Danger Zone → Change visibility → Make public

---

## 二、服务器部署（Docker 方式 - 推荐）

### 1. 连接服务器并安装 Docker

```bash
# 连接服务器
ssh your-user@your-server-ip

# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 安装 Docker Compose
sudo apt install -y docker-compose

# 添加用户到 docker 组
sudo usermod -aG docker $USER

# 重新登录
exit
ssh your-user@your-server-ip
```

### 2. 克隆项目

```bash
# 克隆项目
cd ~
git clone https://github.com/shrekai2025/AutoMoney.git
cd AutoMoney/AutoM2026
```

### 3. 配置环境变量

```bash
# 复制模板
cp .env.example .env

# 编辑配置
vim .env
```

填入你的 API Keys：
```env
FRED_API_KEY=你的_FRED_API_KEY
OPENROUTER_API_KEY=你的_OPENROUTER_KEY
LLM_ENABLED=true
```

### 4. 启动服务

```bash
# 启动
docker-compose up -d

# 查看日志
docker-compose logs -f
```

### 5. 访问应用

浏览器打开：`http://your-server-ip:8080`

---

## 三、服务器部署（直接部署方式）

### 1. 安装依赖

```bash
# 连接服务器
ssh your-user@your-server-ip

# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Python 3.9
sudo apt install -y python3.9 python3.9-venv python3-pip git
```

### 2. 克隆项目

```bash
cd ~
git clone https://github.com/shrekai2025/AutoMoney.git
cd AutoMoney/AutoM2026
```

### 3. 配置环境

```bash
# 复制环境变量模板
cp .env.example .env
vim .env

# 创建虚拟环境
python3.9 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 如果需要 ETF 爬虫功能
playwright install chromium --with-deps
```

### 4. 测试运行

```bash
# 启动服务
python main.py

# 访问 http://your-server-ip:8080
```

### 5. 配置为系统服务

```bash
# 创建服务文件
sudo vim /etc/systemd/system/autom2026.service
```

粘贴以下内容（**替换 your-username**）：

```ini
[Unit]
Description=AutoM2026 Crypto Trading System
After=network.target

[Service]
Type=simple
User=your-username
Group=your-username
WorkingDirectory=/home/your-username/AutoMoney/AutoM2026
Environment="PATH=/home/your-username/AutoMoney/AutoM2026/venv/bin"
ExecStart=/home/your-username/AutoMoney/AutoM2026/venv/bin/python main.py
Restart=always
RestartSec=10

StandardOutput=append:/var/log/autom2026/app.log
StandardError=append:/var/log/autom2026/error.log

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
# 创建日志目录
sudo mkdir -p /var/log/autom2026
sudo chown $USER:$USER /var/log/autom2026

# 启动服务
sudo systemctl daemon-reload
sudo systemctl start autom2026
sudo systemctl enable autom2026

# 查看状态
sudo systemctl status autom2026
```

---

## 四、配置域名和 SSL（可选）

### 1. 安装 Nginx

```bash
sudo apt install -y nginx
```

### 2. 配置反向代理

```bash
sudo vim /etc/nginx/sites-available/autom2026
```

粘贴配置：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用配置：

```bash
sudo ln -s /etc/nginx/sites-available/autom2026 /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 3. 配置 SSL

```bash
# 安装 Certbot
sudo apt install -y certbot python3-certbot-nginx

# 获取证书
sudo certbot --nginx -d your-domain.com

# 测试自动续期
sudo certbot renew --dry-run
```

---

## 五、更新部署

### Docker 方式

```bash
cd ~/AutoMoney/AutoM2026

# 备份数据
cp data/trading.db data/trading.db.backup

# 拉取最新代码
git pull

# 重启容器
docker-compose down
docker-compose up -d --build
```

### 直接部署方式

```bash
cd ~/AutoMoney/AutoM2026

# 备份数据
cp data/trading.db data/trading.db.backup

# 停止服务
sudo systemctl stop autom2026

# 拉取最新代码
git pull

# 更新依赖
source venv/bin/activate
pip install -r requirements.txt

# 重启服务
sudo systemctl start autom2026
```

---

## 六、常用命令

### Docker 部署

```bash
# 查看日志
docker-compose logs -f

# 重启
docker-compose restart

# 停止
docker-compose down

# 查看状态
docker-compose ps
```

### 直接部署

```bash
# 查看状态
sudo systemctl status autom2026

# 查看日志
sudo journalctl -u autom2026 -f

# 重启
sudo systemctl restart autom2026

# 停止
sudo systemctl stop autom2026
```

---

## 七、故障排查

### 服务无法启动

```bash
# 查看日志
docker-compose logs  # Docker 方式
sudo journalctl -u autom2026 -n 100  # 直接部署

# 检查端口占用
sudo netstat -tlnp | grep 8080

# 手动测试
cd ~/AutoMoney/AutoM2026
source venv/bin/activate
python main.py
```

### 无法访问

```bash
# 检查防火墙
sudo ufw status

# 允许端口
sudo ufw allow 8080/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

---

## 八、安全建议

```bash
# 配置防火墙
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# 禁用 root SSH 登录
sudo vim /etc/ssh/sshd_config
# 设置: PermitRootLogin no
sudo systemctl restart sshd
```

---

## 总结

**推荐流程：**

1. 本地推送代码到 GitHub ✅
2. 服务器安装 Docker ✅
3. 克隆项目并配置 .env ✅
4. docker-compose up -d 启动 ✅
5. 配置 Nginx + SSL（可选）✅

**访问地址：**
- 直接访问：http://your-server-ip:8080
- 域名访问：http://your-domain.com
- HTTPS 访问：https://your-domain.com

祝部署顺利！🚀
