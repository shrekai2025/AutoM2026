#!/bin/bash
# AutoM2026 部署测试脚本

echo "=========================================="
echo "  AutoM2026 部署测试"
echo "=========================================="
echo ""

# 获取服务器 IP
if [ -z "$1" ]; then
    echo "请输入服务器 IP 地址:"
    read SERVER_IP
else
    SERVER_IP=$1
fi

echo "测试服务器: $SERVER_IP"
echo ""

# 测试 Web 界面
echo "1. 测试 Web 界面..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://$SERVER_IP:8080 2>/dev/null)
if [ "$HTTP_CODE" = "200" ]; then
    echo "   ✓ Web 界面正常 (HTTP $HTTP_CODE)"
    echo "   访问地址: http://$SERVER_IP:8080"
else
    echo "   ✗ Web 界面无法访问 (HTTP $HTTP_CODE)"
    echo "   请检查服务是否启动和安全组配置"
fi
echo ""

# 测试 API 健康检查
echo "2. 测试 API 健康检查..."
HEALTH=$(curl -s http://$SERVER_IP:8080/api/health 2>/dev/null)
if [ -n "$HEALTH" ]; then
    echo "   ✓ API 健康检查正常"
    echo "   响应: $HEALTH"
else
    echo "   ✗ API 健康检查失败"
fi
echo ""

# 测试 API 文档
echo "3. 测试 API 文档..."
DOCS_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://$SERVER_IP:8080/docs 2>/dev/null)
if [ "$DOCS_CODE" = "200" ]; then
    echo "   ✓ API 文档可访问"
    echo "   访问地址: http://$SERVER_IP:8080/docs"
else
    echo "   ✗ API 文档无法访问 (HTTP $DOCS_CODE)"
fi
echo ""

# 测试端口连通性
echo "4. 测试端口连通性..."
if timeout 3 bash -c "cat < /dev/null > /dev/tcp/$SERVER_IP/8080" 2>/dev/null; then
    echo "   ✓ 端口 8080 可访问"
else
    echo "   ✗ 端口 8080 无法访问"
    echo "   请检查腾讯云安全组是否开放 8080 端口"
fi
echo ""

# 总结
echo "=========================================="
echo "  测试完成"
echo "=========================================="
echo ""
echo "访问方式："
echo "  Web 界面: http://$SERVER_IP:8080"
echo "  API 文档: http://$SERVER_IP:8080/docs"
echo "  API 端点: http://$SERVER_IP:8080/api"
echo ""
echo "如果测试失败，请检查："
echo "  1. 服务是否运行: docker-compose ps"
echo "  2. 查看日志: docker-compose logs"
echo "  3. 腾讯云安全组是否开放 8080 端口"
echo "  4. 服务器防火墙: sudo ufw status"
echo ""
