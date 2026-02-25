#!/bin/bash
# AutoM2026 环境配置脚本

echo "=========================================="
echo "  AutoM2026 环境配置向导"
echo "=========================================="
echo ""

# 检查 .env.example 是否存在
if [ ! -f ".env.example" ]; then
    echo "错误: .env.example 文件不存在"
    exit 1
fi

# 复制模板
cp .env.example .env
echo "✓ 已创建 .env 文件"
echo ""

# 输入 FRED API Key
echo "请输入 FRED API Key:"
echo "（从 https://fredaccount.stlouisfed.org/apikeys 获取）"
read -p "FRED_API_KEY: " fred_key

if [ -n "$fred_key" ]; then
    sed -i "s/your_fred_api_key_here/$fred_key/" .env
    echo "✓ FRED API Key 已配置"
else
    echo "⚠ 跳过 FRED API Key"
fi
echo ""

# 询问是否启用 LLM
read -p "是否启用 LLM 功能? (y/n): " enable_llm

if [ "$enable_llm" = "y" ] || [ "$enable_llm" = "Y" ]; then
    echo "请输入 OpenRouter API Key:"
    echo "（从 https://openrouter.ai/keys 获取）"
    read -p "OPENROUTER_API_KEY: " openrouter_key

    if [ -n "$openrouter_key" ]; then
        sed -i "s/your_openrouter_api_key_here/$openrouter_key/" .env
        sed -i "s/LLM_ENABLED=true/LLM_ENABLED=true/" .env
        echo "✓ OpenRouter API Key 已配置"
    else
        echo "⚠ 跳过 OpenRouter API Key"
    fi
else
    sed -i "s/LLM_ENABLED=true/LLM_ENABLED=false/" .env
    echo "✓ LLM 功能已禁用"
fi
echo ""

# 显示配置结果
echo "=========================================="
echo "  配置完成！"
echo "=========================================="
echo ""
echo "当前配置:"
echo "----------------------------------------"
cat .env | grep -v "^#" | grep -v "^$"
echo "----------------------------------------"
echo ""
echo "如需修改，请编辑 .env 文件:"
echo "  nano .env"
echo ""
echo "或重新运行此脚本:"
echo "  ./setup_env.sh"
echo ""
