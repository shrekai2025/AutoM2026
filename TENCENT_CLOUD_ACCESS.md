# 腾讯云服务器访问指南

部署完成后，有多种方式访问你的 AutoM2026 应用。

---

## 一、获取服务器公网 IP

### 方法 1：在腾讯云控制台查看

1. 登录 [腾讯云控制台](https://console.cloud.tencent.com/)
2. 进入 **云服务器 CVM** → **实例列表**
3. 找到你的服务器，查看 **公网 IP** 列

### 方法 2：在服务器上查询

```bash
# SSH 连接到服务器后执行
curl ifconfig.me

# 或
curl ip.sb

# 或
curl cip.cc
```

假设你的公网 IP 是：`123.45.67.89`

---

## 二、配置安全组（重要！）

腾讯云默认会阻止大部分端口，需要手动开放。

### 1. 在腾讯云控制台配置

1. 进入 **云服务器 CVM** → **实例列表**
2. 点击你的服务器实例
3. 选择 **安全组** 标签
4. 点击 **编辑规则**
5. 添加入站规则：

| 类型 | 来源 | 协议端口 | 策略 | 备注 |
|------|------|----------|------|------|
| 自定义 | 0.0.0.0/0 | TCP:8080 | 允许 | AutoM2026 应用 |
| 自定义 | 0.0.0.0/0 | TCP:80 | 允许 | HTTP（如果配置了 Nginx）|
| 自定义 | 0.0.0.0/0 | TCP:443 | 允许 | HTTPS（如果配置了 SSL）|

### 2. 在服务器上配置防火墙

```bash
# 检查防火墙状态
sudo ufw status

# 如果防火墙已启用，需要开放端口
sudo ufw allow 8080/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# 重新加载防火墙
sudo ufw reload
```

---

## 三、访问 Web 界面

### 方式 1：直接访问（默认端口 8080）

```
http://123.45.67.89:8080
```

在浏览器中打开上面的地址（替换为你的实际 IP）

**页面说明：**
- 首页：策略列表和管理
- 持仓页面：查看当前持仓
- 交易页面：查看历史交易记录

### 方式 2：通过 Nginx 访问（如果配置了）

```
http://123.45.67.89
```

不需要端口号，直接访问 80 端口

### 方式 3：通过域名访问（如果配置了）

```
http://your-domain.com
https://your-domain.com  # 如果配置了 SSL
```

---

## 四、访问 API

AutoM2026 提供 RESTful API 接口。

### API 基础地址

```
http://123.45.67.89:8080/api
```

### 常用 API 端点

#### 1. 健康检查

```bash
curl http://123.45.67.89:8080/api/health
```

返回示例：
```json
{
  "status": "ok",
  "timestamp": "2026-02-25T10:30:00"
}
```

#### 2. 获取策略列表

```bash
curl http://123.45.67.89:8080/api/strategies
```

#### 3. 获取持仓信息

```bash
curl http://123.45.67.89:8080/api/positions
```

#### 4. 获取交易历史

```bash
curl http://123.45.67.89:8080/api/trades
```

#### 5. 执行策略

```bash
curl -X POST http://123.45.67.89:8080/api/strategies/{strategy_id}/execute
```

### 使用 Postman 测试 API

1. 下载 [Postman](https://www.postman.com/downloads/)
2. 创建新请求
3. 设置 Base URL: `http://123.45.67.89:8080`
4. 测试各个端点

---

## 五、查看 API 文档

AutoM2026 使用 FastAPI，自带交互式 API 文档。

### Swagger UI（推荐）

```
http://123.45.67.89:8080/docs
```

**功能：**
- ✅ 查看所有 API 端点
- ✅ 查看请求/响应格式
- ✅ 直接在浏览器中测试 API
- ✅ 自动生成示例代码

### ReDoc（备选）

```
http://123.45.67.89:8080/redoc
```

更简洁的文档界面

---

## 六、常见访问问题

### 问题 1：无法访问，连接超时

**原因：** 安全组未开放端口

**解决：**
```bash
# 1. 检查服务是否运行
docker-compose ps  # Docker 方式
sudo systemctl status autom2026  # 直接部署

# 2. 检查端口监听
sudo netstat -tlnp | grep 8080

# 3. 在腾讯云控制台开放安全组端口（见上文）

# 4. 检查服务器防火墙
sudo ufw status
sudo ufw allow 8080/tcp
```

### 问题 2：访问显示 502 Bad Gateway

**原因：** Nginx 配置了但后端服务未启动

**解决：**
```bash
# 检查后端服务
docker-compose logs  # Docker 方式
sudo journalctl -u autom2026 -f  # 直接部署

# 重启服务
docker-compose restart
# 或
sudo systemctl restart autom2026
```

### 问题 3：页面加载很慢

**原因：** 服务器带宽不足或资源占用高

**解决：**
```bash
# 查看资源使用
htop

# 查看网络连接
sudo netstat -an | grep 8080

# 优化：配置 Nginx 缓存（见完整文档）
```

---

## 七、测试部署是否成功

### 快速测试脚本

```bash
# 在本地或服务器上运行
SERVER_IP="123.45.67.89"  # 替换为你的 IP

echo "测试 Web 界面..."
curl -I http://$SERVER_IP:8080

echo -e "\n测试 API 健康检查..."
curl http://$SERVER_IP:8080/api/health

echo -e "\n测试 API 文档..."
curl -I http://$SERVER_IP:8080/docs

echo -e "\n如果以上都返回 200 OK，说明部署成功！"
```

### 完整测试清单

- [ ] Web 界面可以打开：`http://IP:8080`
- [ ] API 文档可以访问：`http://IP:8080/docs`
- [ ] 健康检查返回正常：`curl http://IP:8080/api/health`
- [ ] 可以查看策略列表
- [ ] 可以创建新策略
- [ ] 可以执行策略

---

## 八、配置域名访问（可选）

如果你有域名，可以配置更友好的访问方式。

### 1. 域名解析

在你的域名服务商（如腾讯云 DNSPod）添加 A 记录：

```
类型: A
主机记录: @ 或 www
记录值: 123.45.67.89（你的服务器 IP）
TTL: 600
```

### 2. 配置 Nginx

参考 `README_DEPLOY.md` 中的 Nginx 配置部分

### 3. 配置 SSL

```bash
sudo certbot --nginx -d your-domain.com
```

配置完成后访问：
```
https://your-domain.com
```

---

## 九、安全建议

### 1. 不要暴露所有端口

如果只是个人使用，可以限制访问来源：

```bash
# 在腾讯云安全组中，将来源改为你的 IP
# 例如：123.45.67.89/32（只允许你的 IP 访问）
```

### 2. 配置基础认证

如果担心安全，可以在 Nginx 中配置密码保护：

```bash
# 安装工具
sudo apt install -y apache2-utils

# 创建密码文件
sudo htpasswd -c /etc/nginx/.htpasswd admin

# 在 Nginx 配置中添加
location / {
    auth_basic "Restricted Access";
    auth_basic_user_file /etc/nginx/.htpasswd;
    proxy_pass http://127.0.0.1:8080;
}
```

### 3. 使用 HTTPS

强烈建议配置 SSL 证书，保护数据传输安全。

---

## 十、监控访问日志

### 查看访问日志

```bash
# Docker 方式
docker-compose logs -f

# 直接部署
sudo journalctl -u autom2026 -f

# Nginx 访问日志
sudo tail -f /var/log/nginx/access.log
```

### 查看实时连接

```bash
# 查看当前连接数
sudo netstat -an | grep :8080 | wc -l

# 查看连接详情
sudo netstat -an | grep :8080
```

---

## 总结

### 快速访问清单

1. **获取 IP**：腾讯云控制台查看
2. **开放端口**：安全组添加 8080 端口
3. **访问 Web**：`http://IP:8080`
4. **访问 API**：`http://IP:8080/docs`
5. **测试健康**：`curl http://IP:8080/api/health`

### 推荐访问方式

- **开发测试**：直接 IP + 端口访问
- **生产使用**：配置域名 + Nginx + SSL

### 获取帮助

如果访问遇到问题：
1. 检查服务是否运行：`docker-compose ps`
2. 查看日志：`docker-compose logs`
3. 检查端口：`sudo netstat -tlnp | grep 8080`
4. 检查安全组：腾讯云控制台
5. 查看详细文档：`UBUNTU_DEPLOY_GUIDE.md`

---

**祝你使用愉快！** 🚀
