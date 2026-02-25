# AutoM2026 Ubuntu 服务器部署指南

## 项目概述

AutoM2026 是一个简化版加密货币策略交易系统，支持技术指标、宏观趋势和网格交易策略。

**技术栈:**
- 后端: FastAPI + SQLite + APScheduler
- 前端: Jinja2 模板
- 部署: Docker / Systemd

---

## 部署方式选择

### 方式一：Docker 部署（推荐）
- ✅ 简单快速，一键部署
- ✅ 环境隔离，不污染系统
- ✅ 易于更新和回滚

### 方式二：直接部署
- ✅ 性能更好
- ✅ 更灵活的配置
- ⚠️ 需要手动管理依赖

---

## 方式一：Docker 部署（推荐新手）

### 1. 服务器准备

```bash
# 连接到服务器
ssh your-user@your-server-ip

# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 安装 Docker Compose
sudo apt install -y docker-compose

# 将当前用户添加到 docker 组
sudo usermod -aG docker $USER

# 重新登录使权限生效
exit
ssh your-user@your-server-ip
```

### 2. 克隆项目代码

```bash
# 在服务器上克隆项目
cd ~
git clone https://github.com/shrekai2025/AutoMoney.git
cd AutoMoney/AutoM2026

# 或者克隆到指定目录
git clone https://github.com/shrekai2025/AutoMoney.git autom2026
cd autom2026/AutoM2026
```

### 3. 配置环境变量

```bash
cd ~/AutoMoney/AutoM2026

# 复制环境变量模板
cp .env.example .env

# 编辑并填入你的 API Keys
vim .env
```

**必须配置的项：**
- `FRED_API_KEY`: 从 https://fred.stlouisfed.org/docs/api/api_key.html 获取
- `OPENROUTER_API_KEY`: 从 https://openrouter.ai/ 获取（如果启用 LLM）
- `LLM_ENABLED`: 设置为 `true` 或 `false`

### 4. 启动服务

```bash
# 构建并启动容器
docker-compose up -d

# 查看日志
docker-compose logs -f

# 检查容器状态
docker-compose ps
```

### 5. 配置 Nginx 反向代理（可选）

```bash
# 安装 Nginx
sudo apt install -y nginx

# 创建配置文件
sudo vim /etc/nginx/sites-available/autom2026
```

粘贴以下配置：

```nginx
server {
    listen 80;
    server_name your-domain.com;  # 替换为你的域名或 IP

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
```

启用配置：

```bash
# 创建软链接
sudo ln -s /etc/nginx/sites-available/autom2026 /etc/nginx/sites-enabled/

# 测试配置
sudo nginx -t

# 重启 Nginx
sudo systemctl restart nginx
```

### 6. 配置 SSL（可选但推荐）

```bash
# 安装 Certbot
sudo apt install -y certbot python3-certbot-nginx

# 获取 SSL 证书
sudo certbot --nginx -d your-domain.com

# 测试自动续期
sudo certbot renew --dry-run
```

### Docker 常用命令

```bash
# 查看日志
docker-compose logs -f

# 重启服务
docker-compose restart

# 停止服务
docker-compose down

# 更新代码后重新构建
docker-compose up -d --build

# 进入容器
docker-compose exec autom2026 bash

# 查看容器资源使用
docker stats
```

---

## 方式二：直接部署（适合进阶用户）

### 1. 服务器准备

```bash
# 连接到服务器
ssh your-user@your-server-ip

# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装基础工具
sudo apt install -y git curl wget vim build-essential
```

### 2. 安装 Python 3.9+

```bash
# 安装 Python 3.9
sudo apt install -y python3.9 python3.9-venv python3.9-dev python3-pip

# 验证安装
python3.9 --version
```

### 3. 创建部署用户（可选）

```bash
# 创建专用用户
sudo adduser autom2026
sudo usermod -aG sudo autom2026

# 切换到新用户
su - autom2026
```

### 4. 克隆项目

```bash
# 克隆项目
cd ~
git clone https://github.com/shrekai2025/AutoMoney.git
cd AutoMoney/AutoM2026
```

### 5. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑并填入你的 API Keys
vim .env
```

### 6. 安装依赖

```bash
# 创建虚拟环境
python3.9 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install --upgrade pip
pip install -r requirements.txt

# 安装 Playwright 浏览器（如果需要 ETF 爬虫功能）
playwright install chromium --with-deps
```

### 7. 初始化数据目录

```bash
# 创建必要的目录
mkdir -p data logs

# 设置权限
chmod 755 data logs
```

### 8. 测试运行

```bash
# 激活虚拟环境
source venv/bin/activate

# 启动服务
python main.py

# 在另一个终端测试
curl http://localhost:8080
```

### 9. 配置 Systemd 服务

```bash
# 创建服务文件
sudo vim /etc/systemd/system/autom2026.service
```

粘贴以下内容（**注意修改用户名和路径**）：

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

# 日志配置
StandardOutput=append:/var/log/autom2026/app.log
StandardError=append:/var/log/autom2026/error.log

[Install]
WantedBy=multi-user.target
```

**重要**: 将 `your-username` 替换为你的实际用户名

创建日志目录：

```bash
# 创建日志目录
sudo mkdir -p /var/log/autom2026
sudo chown autom2026:autom2026 /var/log/autom2026
```

启动服务：

```bash
# 重新加载 systemd
sudo systemctl daemon-reload

# 启动服务
sudo systemctl start autom2026

# 设置开机自启
sudo systemctl enable autom2026

# 查看状态
sudo systemctl status autom2026

# 查看日志
sudo journalctl -u autom2026 -f
```

### 10. 配置 Nginx（同 Docker 方式）

参考上面 Docker 部署的 Nginx 配置部分。

---

## 数据持久化

### Docker 部署

数据已通过 docker-compose.yml 映射到宿主机：

```bash
# 数据库位置
~/autom2026/data/

# 日志位置
~/autom2026/logs/
```

### 直接部署

数据默认存储在项目目录：

```bash
# 数据库
~/autom2026/data/trading.db

# 日志
~/autom2026/logs/
```

---

## 备份策略

### 创建备份脚本

```bash
# 创建备份脚本
cat > ~/backup_autom2026.sh << 'EOF'
#!/bin/bash

BACKUP_DIR="$HOME/backups/autom2026"
DATE=$(date +%Y%m%d_%H%M%S)
PROJECT_DIR="$HOME/autom2026"

# 创建备份目录
mkdir -p $BACKUP_DIR

# 备份数据库
cp $PROJECT_DIR/data/trading.db $BACKUP_DIR/trading_$DATE.db

# 备份配置
cp $PROJECT_DIR/.env $BACKUP_DIR/env_$DATE.bak

# 压缩旧备份
find $BACKUP_DIR -name "*.db" -mtime +7 -exec gzip {} \;

# 删除 30 天前的备份
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete

echo "Backup completed: $DATE"
EOF

chmod +x ~/backup_autom2026.sh
```

### 设置定时备份

```bash
# 编辑 crontab
crontab -e

# 添加每天凌晨 2 点备份
0 2 * * * /home/autom2026/backup_autom2026.sh >> /home/autom2026/backup.log 2>&1
```

---

## 监控和维护

### 查看日志

```bash
# Docker 部署
docker-compose logs -f

# 直接部署
sudo journalctl -u autom2026 -f
tail -f /var/log/autom2026/app.log
```

### 查看系统资源

```bash
# 安装 htop
sudo apt install -y htop

# 查看资源使用
htop

# Docker 资源使用
docker stats
```

### 重启服务

```bash
# Docker 部署
docker-compose restart

# 直接部署
sudo systemctl restart autom2026
```

---

## 更新部署

### Docker 部署更新

```bash
cd ~/AutoMoney/AutoM2026

# 备份数据
cp data/trading.db data/trading.db.backup.$(date +%Y%m%d_%H%M%S)

# 拉取最新代码
git pull

# 重新构建并启动
docker-compose down
docker-compose up -d --build

# 查看日志确认启动成功
docker-compose logs -f
```

### 直接部署更新

```bash
cd ~/AutoMoney/AutoM2026

# 备份数据
cp data/trading.db data/trading.db.backup.$(date +%Y%m%d_%H%M%S)

# 停止服务
sudo systemctl stop autom2026

# 拉取最新代码
git pull

# 激活虚拟环境
source venv/bin/activate

# 更新依赖
pip install -r requirements.txt

# 启动服务
sudo systemctl start autom2026

# 查看日志
sudo journalctl -u autom2026 -f
```

---

## 安全建议

### 1. 配置防火墙

```bash
# 安装 UFW
sudo apt install -y ufw

# 允许 SSH
sudo ufw allow 22/tcp

# 允许 HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# 启用防火墙
sudo ufw enable

# 查看状态
sudo ufw status
```

### 2. 禁用 Root SSH 登录

```bash
# 编辑 SSH 配置
sudo vim /etc/ssh/sshd_config

# 修改以下配置
PermitRootLogin no
PasswordAuthentication no  # 使用密钥登录

# 重启 SSH 服务
sudo systemctl restart sshd
```

### 3. 安装 Fail2ban

```bash
# 安装 Fail2ban
sudo apt install -y fail2ban

# 启动服务
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### 4. 定期更新系统

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 自动安全更新
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

---

## 故障排查

### 服务无法启动

```bash
# Docker 部署
docker-compose logs

# 直接部署
sudo journalctl -u autom2026 -n 100

# 检查端口占用
sudo netstat -tlnp | grep 8080

# 手动启动测试
cd ~/autom2026
source venv/bin/activate
python main.py
```

### 数据库问题

```bash
# 检查数据库文件
ls -lh ~/autom2026/data/trading.db

# 检查权限
sudo chown -R autom2026:autom2026 ~/autom2026/data/
```

### 内存不足

```bash
# 查看内存使用
free -h

# 创建 swap 文件（如果内存小于 2GB）
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 永久启用
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

## 性能优化

### 1. 调整 Uvicorn Workers

编辑 `main.py`，根据 CPU 核心数调整：

```python
# 对于 2 核 CPU
uvicorn.run(
    "web.app:app",
    host=WEB_HOST,
    port=WEB_PORT,
    workers=2,  # 调整这里
    log_level=LOG_LEVEL.lower(),
)
```

### 2. 配置日志轮转

```bash
# 创建 logrotate 配置
sudo vim /etc/logrotate.d/autom2026
```

```
/var/log/autom2026/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 autom2026 autom2026
    sharedscripts
    postrotate
        systemctl reload autom2026 > /dev/null 2>&1 || true
    endscript
}
```

---

## 常用命令速查

### Docker 部署

```bash
# 启动
docker-compose up -d

# 停止
docker-compose down

# 重启
docker-compose restart

# 查看日志
docker-compose logs -f

# 重新构建
docker-compose up -d --build
```

### 直接部署

```bash
# 启动
sudo systemctl start autom2026

# 停止
sudo systemctl stop autom2026

# 重启
sudo systemctl restart autom2026

# 查看状态
sudo systemctl status autom2026

# 查看日志
sudo journalctl -u autom2026 -f
```

---

## 访问应用

部署完成后，通过以下方式访问：

- **本地访问**: http://your-server-ip:8080
- **域名访问**: http://your-domain.com（配置 Nginx 后）
- **HTTPS 访问**: https://your-domain.com（配置 SSL 后）

---

## 获取帮助

如遇到问题：

1. 查看应用日志
2. 查看系统日志：`sudo journalctl -xe`
3. 检查服务状态：`systemctl status autom2026`
4. 检查端口占用：`sudo netstat -tlnp`

---

## 总结

推荐部署流程：

1. **新手**: 使用 Docker 部署 → 配置 Nginx → 配置 SSL
2. **进阶**: 直接部署 → Systemd 服务 → Nginx → SSL
3. **必做**: 配置防火墙 → 设置备份 → 禁用 Root 登录

祝部署顺利！🚀
