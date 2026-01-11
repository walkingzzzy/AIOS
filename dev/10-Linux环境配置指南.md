# AIOS Protocol Linux 环境配置指南

**版本**: 2.0.0  
**更新日期**: 2026-01-11  
**文档类型**: 📋 环境配置指南

---

## 一、概述

本文档提供 AIOS Protocol 在 Linux 平台上的环境配置指南，包括必要的系统依赖和工具安装。

**支持的发行版**:
- Ubuntu 22.04+ / Debian 12+
- Fedora 38+
- Arch Linux

---

## 二、基础环境

### 2.1 Node.js 安装

```bash
# Ubuntu/Debian - 使用 NodeSource
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Fedora
sudo dnf install nodejs

# Arch Linux
sudo pacman -S nodejs npm

# 验证安装
node --version  # 应显示 v20.x.x
npm --version
```

### 2.2 pnpm 安装

```bash
# 使用 npm 安装
npm install -g pnpm

# 或使用 corepack (Node.js 16.13+)
corepack enable
corepack prepare pnpm@latest --activate

# 验证安装
pnpm --version
```

### 2.3 构建工具 (node-gyp 依赖)

```bash
# Ubuntu/Debian
sudo apt-get install -y build-essential python3

# Fedora
sudo dnf groupinstall "Development Tools"
sudo dnf install python3

# Arch Linux
sudo pacman -S base-devel python
```

---

## 三、系统控制依赖

### 3.1 亮度控制 (brightness)

**问题**: `brightness` npm 包在 Linux 上需要 `brightnessctl` 或 `xbacklight`

```bash
# Ubuntu/Debian - 推荐 brightnessctl
sudo apt-get install -y brightnessctl

# Fedora
sudo dnf install brightnessctl

# Arch Linux
sudo pacman -S brightnessctl

# 验证安装
brightnessctl --version
brightnessctl get  # 获取当前亮度
```

**权限配置** (如果遇到权限问题):

```bash
# 添加用户到 video 组
sudo usermod -aG video $USER

# 创建 udev 规则
sudo tee /etc/udev/rules.d/90-backlight.rules << EOF
SUBSYSTEM=="backlight", ACTION=="add", RUN+="/bin/chgrp video /sys/class/backlight/%k/brightness", RUN+="/bin/chmod g+w /sys/class/backlight/%k/brightness"
EOF

# 重新加载 udev 规则
sudo udevadm control --reload-rules
sudo udevadm trigger

# 重新登录生效
```

### 3.2 音量控制 (loudness)

**依赖**: PulseAudio 或 PipeWire

```bash
# Ubuntu/Debian - 通常已预装
sudo apt-get install -y pulseaudio-utils

# Fedora (PipeWire)
sudo dnf install pipewire-pulseaudio

# Arch Linux
sudo pacman -S pulseaudio-alsa
# 或 PipeWire
sudo pacman -S pipewire-pulse

# 验证
pactl get-sink-volume @DEFAULT_SINK@
```

### 3.3 截图工具 (screenshot-desktop)

```bash
# Ubuntu/Debian (GNOME)
sudo apt-get install -y gnome-screenshot

# 或使用 scrot (更轻量)
sudo apt-get install -y scrot

# Fedora
sudo dnf install gnome-screenshot

# Arch Linux
sudo pacman -S gnome-screenshot
# 或
sudo pacman -S scrot
```

### 3.4 剪贴板工具

```bash
# X11 环境
sudo apt-get install -y xclip xsel

# Wayland 环境
sudo apt-get install -y wl-clipboard

# Fedora
sudo dnf install xclip wl-clipboard

# Arch Linux
sudo pacman -S xclip wl-clipboard
```

### 3.5 窗口管理 (nut.js)

**X11 依赖**:

```bash
# Ubuntu/Debian
sudo apt-get install -y \
    libxtst-dev \
    libpng-dev \
    libx11-dev \
    libxkbcommon-x11-dev

# Fedora
sudo dnf install \
    libXtst-devel \
    libpng-devel \
    libX11-devel \
    libxkbcommon-x11-devel

# Arch Linux
sudo pacman -S \
    libxtst \
    libpng \
    libx11 \
    libxkbcommon-x11
```

**Wayland 注意事项**:
- nut.js 主要支持 X11
- Wayland 环境下部分功能可能受限
- 建议使用 XWayland 兼容层

---

## 四、浏览器控制依赖

### 4.1 Playwright 依赖

```bash
# 安装 Playwright 浏览器
npx playwright install

# 安装系统依赖 (Ubuntu/Debian)
npx playwright install-deps

# 手动安装依赖 (如果上述命令失败)
sudo apt-get install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2
```

---

## 五、桌面环境特定配置

### 5.1 GNOME

```bash
# 壁纸设置依赖
# wallpaper npm 包使用 gsettings，通常已预装

# 深色模式切换
gsettings get org.gnome.desktop.interface color-scheme
gsettings set org.gnome.desktop.interface color-scheme 'prefer-dark'
```

### 5.2 KDE Plasma

```bash
# 壁纸设置
# wallpaper npm 包支持 KDE

# 深色模式 - 使用 plasma-apply-colorscheme
plasma-apply-colorscheme BreezeDark
```

### 5.3 Xfce

```bash
# 壁纸设置依赖
sudo apt-get install -y xfconf

# 深色模式
xfconf-query -c xsettings -p /Net/ThemeName -s "Adwaita-dark"
```

---

## 六、一键安装脚本

### 6.1 Ubuntu/Debian

```bash
#!/bin/bash
# AIOS Protocol Linux 依赖安装脚本 (Ubuntu/Debian)

set -e

# 错误处理函数
handle_error() {
    echo "❌ 错误: 安装在第 $1 行失败"
    echo "请检查错误信息并手动修复后重试"
    exit 1
}

trap 'handle_error $LINENO' ERR

echo "=== AIOS Protocol Linux 环境配置 ==="
echo "开始时间: $(date)"
echo ""

# 检查是否为 root 用户
if [ "$EUID" -eq 0 ]; then
    echo "⚠️  警告: 请勿以 root 用户运行此脚本"
    echo "请使用普通用户运行，脚本会在需要时请求 sudo 权限"
    exit 1
fi

# 更新包列表
echo "📦 更新包列表..."
sudo apt-get update || { echo "❌ 更新包列表失败"; exit 1; }

# 基础构建工具
echo "🔧 安装构建工具..."
sudo apt-get install -y build-essential python3

# 亮度控制
echo "💡 安装亮度控制工具..."
sudo apt-get install -y brightnessctl

# 音频控制
echo "🔊 安装音频控制工具..."
sudo apt-get install -y pulseaudio-utils

# 截图工具
echo "📸 安装截图工具..."
sudo apt-get install -y gnome-screenshot scrot

# 剪贴板工具
echo "📋 安装剪贴板工具..."
sudo apt-get install -y xclip xsel wl-clipboard

# nut.js 依赖
echo "🖱️  安装 nut.js 依赖..."
sudo apt-get install -y \
    libxtst-dev \
    libpng-dev \
    libx11-dev \
    libxkbcommon-x11-dev

# Playwright 依赖
echo "🌐 安装 Playwright 依赖..."
sudo apt-get install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2

# 配置亮度权限
echo "🔐 配置亮度控制权限..."
if ! groups $USER | grep -q '\bvideo\b'; then
    sudo usermod -aG video $USER
    echo "✅ 已将用户 $USER 添加到 video 组"
else
    echo "ℹ️  用户 $USER 已在 video 组中"
fi

echo ""
echo "=== ✅ 安装完成 ==="
echo "结束时间: $(date)"
echo ""
echo "⚠️  重要提示:"
echo "   1. 请重新登录以使 video 组权限生效"
echo "   2. 运行 ./verify-aios-deps.sh 验证安装"
echo ""
```

### 6.2 Fedora

```bash
#!/bin/bash
# AIOS Protocol Linux 依赖安装脚本 (Fedora)

set -e

# 错误处理函数
handle_error() {
    echo "❌ 错误: 安装在第 $1 行失败"
    echo "请检查错误信息并手动修复后重试"
    exit 1
}

trap 'handle_error $LINENO' ERR

echo "=== AIOS Protocol Linux 环境配置 (Fedora) ==="
echo "开始时间: $(date)"
echo ""

# 检查是否为 root 用户
if [ "$EUID" -eq 0 ]; then
    echo "⚠️  警告: 请勿以 root 用户运行此脚本"
    exit 1
fi

# 基础构建工具
echo "🔧 安装构建工具..."
sudo dnf groupinstall -y "Development Tools"
sudo dnf install -y python3

# 系统控制工具
echo "🔧 安装系统控制工具..."
sudo dnf install -y \
    brightnessctl \
    pipewire-pulseaudio \
    gnome-screenshot \
    xclip \
    wl-clipboard

# nut.js 依赖
echo "🖱️  安装 nut.js 依赖..."
sudo dnf install -y \
    libXtst-devel \
    libpng-devel \
    libX11-devel \
    libxkbcommon-x11-devel

# 配置亮度权限
echo "🔐 配置亮度控制权限..."
if ! groups $USER | grep -q '\bvideo\b'; then
    sudo usermod -aG video $USER
    echo "✅ 已将用户 $USER 添加到 video 组"
fi

echo ""
echo "=== ✅ 安装完成 ==="
echo "结束时间: $(date)"
echo ""
echo "⚠️  请重新登录以使权限生效"
```

---

## 七、验证安装

```bash
# 创建验证脚本
cat > verify-aios-deps.sh << 'EOF'
#!/bin/bash

echo "=== AIOS Protocol 依赖验证 ==="

check_command() {
    if command -v $1 &> /dev/null; then
        echo "✅ $1: $(command -v $1)"
    else
        echo "❌ $1: 未安装"
    fi
}

check_command node
check_command npm
check_command pnpm
check_command brightnessctl
check_command pactl
check_command gnome-screenshot
check_command xclip

echo ""
echo "Node.js 版本: $(node --version 2>/dev/null || echo '未安装')"
echo "npm 版本: $(npm --version 2>/dev/null || echo '未安装')"
echo "pnpm 版本: $(pnpm --version 2>/dev/null || echo '未安装')"

EOF

chmod +x verify-aios-deps.sh
./verify-aios-deps.sh
```

---

## 八、常见问题

### Q1: brightnessctl 权限被拒绝

```bash
# 解决方案 1: 添加到 video 组
sudo usermod -aG video $USER
# 重新登录

# 解决方案 2: 使用 sudo
sudo brightnessctl set 50%
```

### Q2: nut.js 安装失败

```bash
# 确保安装了所有依赖
sudo apt-get install -y libxtst-dev libpng-dev

# 清理 npm 缓存重试
npm cache clean --force
npm install @nut-tree/nut-js
```

### Q3: Playwright 浏览器启动失败

```bash
# 安装缺失的依赖
npx playwright install-deps chromium

# 或手动安装
sudo apt-get install -y libnss3 libatk-bridge2.0-0
```

### Q4: Wayland 下键鼠模拟不工作

```bash
# 检查是否在 Wayland 环境
echo $XDG_SESSION_TYPE

# 如果是 wayland，切换到 X11 会话
# 或使用 XWayland 兼容
```

---

## 九、参考链接

- [Node.js 官方安装指南](https://nodejs.org/en/download/package-manager)
- [pnpm 安装文档](https://pnpm.io/installation)
- [Playwright Linux 依赖](https://playwright.dev/docs/intro#system-requirements)
- [nut.js 文档](https://nutjs.dev/)
- [brightnessctl GitHub](https://github.com/Hummer12007/brightnessctl)

---

**文档版本**: 2.0.0  
**维护者**: AIOS Protocol Team

