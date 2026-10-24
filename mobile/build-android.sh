#!/bin/bash
# ============================================================
# 天链运维 - Android APK 打包脚本
# 版本: 1.0.0
# 日期: 2026-05-18
# ============================================================
set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo_info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
echo_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }
echo_ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }

# ============================================================
# 配置区域 - 根据实际情况修改
# ============================================================

# 项目路径
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# 构建类型: apk | aab
BUILD_TYPE="${BUILD_TYPE:-apk}"

# 构建Profile: development | preview | production
BUILD_PROFILE="${BUILD_PROFILE:-production}"

# 输出目录
OUTPUT_DIR="${PROJECT_DIR}/builds"
mkdir -p "$OUTPUT_DIR"

# Android Keystore 签名配置
# ⚠️ 生产环境请修改以下路径和密码
KEYSTORE_PATH="${KEYSTORE_PATH:-${PROJECT_DIR}/android/app/tianlian.keystore}"
KEYSTORE_ALIAS="${KEYSTORE_ALIAS:-tianlian}"
KEYSTORE_PASSWORD="${KEYSTORE_PASSWORD:-}"
KEYSTORE_KEY_PASSWORD="${KEYSTORE_KEY_PASSWORD:-}"

# 版本信息
APP_VERSION="${APP_VERSION:-1.0.0}"
BUILD_NUMBER="${BUILD_NUMBER:-1}"

# ============================================================
# 函数定义
# ============================================================

print_banner() {
  echo ""
  echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}║       天链运维 Android APK 打包工具        ║${NC}"
  echo -e "${GREEN}║           TianLian Build Script            ║${NC}"
  echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"
  echo ""
  echo_info "项目路径: ${PROJECT_DIR}"
  echo_info "构建类型: ${BUILD_TYPE}"
  echo_info "构建配置: ${BUILD_PROFILE}"
  echo_info "应用版本: ${APP_VERSION} (build ${BUILD_NUMBER})"
  echo ""
}

# 检查依赖环境
check_environment() {
  echo_info "检查依赖环境..."
  
  # 检查 Node.js
  if ! command -v node &> /dev/null; then
    echo_error "未安装 Node.js，请先安装 Node.js (>= 16.x)"
    exit 1
  fi
  echo_ok "Node.js $(node -v)"
  
  # 检查 npm
  if ! command -v npm &> /dev/null; then
    echo_error "未安装 npm"
    exit 1
  fi
  echo_ok "npm $(npm -v)"
  
  # 检查 node_modules
  if [ ! -d "node_modules" ]; then
    echo_warn "node_modules 不存在，正在安装依赖..."
    npm install
  fi
  echo_ok "node_modules 已就绪"
  
  # 检查 EAS CLI
  if command -v eas &> /dev/null; then
    echo_ok "EAS CLI $(eas --version)"
    EAS_AVAILABLE=true
  else
    echo_warn "EAS CLI 未安装（将使用 expo 备用方案）"
    EAS_AVAILABLE=false
  fi
  
  # 检查 Expo CLI
  if command -v npx &> /dev/null; then
    echo_ok "npx 可用"
  fi
}

# 检查必需文件
check_files() {
  echo_info "检查项目文件完整性..."
  
  local required_files=(
    "app.json"
    "app.config.js"
    "babel.config.js"
    "package.json"
    "App.tsx"
    "assets/icon.png"
    "assets/splash.png"
    "assets/adaptive-icon.png"
    "eas.json"
  )
  
  local all_ok=true
  for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
      echo_ok "[✓] $file"
    else
      echo_error "[✗] $file - 缺失"
      all_ok=false
    fi
  done
  
  if [ "$all_ok" = false ]; then
    echo_error "缺少必需文件，请检查后再构建"
    exit 1
  fi
  echo_ok "所有必需文件已就绪"
}

# TypeScript 类型检查
type_check() {
  echo_info "执行 TypeScript 类型检查..."
  
  if [ -f "tsconfig.json" ]; then
    if npx tsc --noEmit 2>&1; then
      echo_ok "TypeScript 检查通过"
    else
      echo_warn "TypeScript 检查有警告（不阻塞构建）"
    fi
  else
    echo_warn "tsconfig.json 不存在，跳过类型检查"
  fi
}

# 生成 Android Keystore (如果不存在)
generate_keystore() {
  if [ -f "$KEYSTORE_PATH" ]; then
    echo_ok "Keystore 已存在: $KEYSTORE_PATH"
    return
  fi
  
  echo_warn "Keystore 不存在，正在生成..."
  echo_info "请设置以下环境变量:"
  echo_info "  KEYSTORE_PASSWORD     - Keystore 密码"
  echo_info "  KEYSTORE_KEY_PASSWORD - Key 密码"
  echo ""
  
  if [ -z "$KEYSTORE_PASSWORD" ]; then
    read -sp "请输入 Keystore 密码: " KEYSTORE_PASSWORD
    echo ""
  fi
  if [ -z "$KEYSTORE_KEY_PASSWORD" ]; then
    read -sp "请输入 Key 密码 (与Keystore密码相同): " KEYSTORE_KEY_PASSWORD
    echo ""
  fi
  
  keytool -genkey -v \
    -keystore "$KEYSTORE_PATH" \
    -alias "$KEYSTORE_ALIAS" \
    -keyalg RSA \
    -keysize 2048 \
    -validity 10000 \
    -storepass "$KEYSTORE_PASSWORD" \
    -keypass "$KEYSTORE_KEY_PASSWORD" \
    -dname "CN=TianLian Ops, OU=Engineering, O=TianLian Tech, L=Beijing, ST=Beijing, C=CN"
  
  echo_ok "Keystore 已生成: $KEYSTORE_PATH"
  echo_warn "⚠️ 请妥善保管 Keystore 文件和密码！丢失后无法更新应用！"
}

# 配置 Gradle 签名
configure_gradle_signing() {
  if [ ! -f "android/app/build.gradle" ]; then
    echo_warn "android/app/build.gradle 不存在，请先运行: npx expo prebuild"
    return
  fi
  
  echo_info "配置 Gradle 签名..."
  
  # 检查是否已配置签名
  if grep -q "storeFile file" "android/app/build.gradle" 2>/dev/null; then
    echo_ok "Gradle 签名已配置"
    return
  fi
  
  # 备份原文件
  cp "android/app/build.gradle" "android/app/build.gradle.bak"
  
  # 在 android {} 块中添加签名配置
  local keystore_path=$(cd "$(dirname "$KEYSTORE_PATH")" && pwd)/$(basename "$KEYSTORE_PATH")
  
  echo_warn "请手动在 android/app/build.gradle 的 android {} 块中添加以下配置:"
  echo ""
  echo -e "${YELLOW}signingConfigs {${NC}"
  echo -e "${YELLOW}    release {${NC}"
  echo -e "${YELLOW}        storeFile file('${keystore_path}')${NC}"
  echo -e "${YELLOW}        storePassword '${KEYSTORE_PASSWORD}'${NC}"
  echo -e "${YELLOW}        keyAlias '${KEYSTORE_ALIAS}'${NC}"
  echo -e "${YELLOW}        keyPassword '${KEYSTORE_KEY_PASSWORD}'${NC}"
  echo -e "${YELLOW}    }${NC}"
  echo -e "${YELLOW}}${NC}"
  echo ""
  echo -e "${YELLOW}buildTypes {${NC}"
  echo -e "${YELLOW}    release {${NC}"
  echo -e "${YELLOW}        signingConfig signingConfigs.release${NC}"
  echo -e "${YELLOW}    }${NC}"
  echo -e "${YELLOW}}${NC}"
  echo ""
}

# EAS Build 打包 (推荐方式)
build_with_eas() {
  echo_info "使用 EAS Build 打包..."
  echo_info "构建 Profile: ${BUILD_PROFILE}"
  
  export APP_VERSION="${APP_VERSION}"
  export BUILD_NUMBER="${BUILD_NUMBER}"
  
  if [ "$BUILD_TYPE" = "aab" ]; then
    echo_info "构建 Android App Bundle (AAB)..."
    npx eas build \
      --platform android \
      --profile "$BUILD_PROFILE" \
      --non-interactive \
      --auto-submit
  else
    echo_info "构建 Android APK..."
    npx eas build \
      --platform android \
      --profile "$BUILD_PROFILE" \
      --non-interactive
  fi
  
  if [ $? -eq 0 ]; then
    echo_ok "EAS Build 提交成功！"
    echo_info "你可以在 Expo 控制台查看构建进度:"
    echo_info "  https://expo.dev/accounts/[your-account]/projects/tianlian-v3/builds"
  else
    echo_error "EAS Build 失败"
    exit 1
  fi
}

# Expo Classic Build 打包 (备用方案)
build_with_expo() {
  echo_info "使用 Expo Classic Build 打包..."
  
  # Expo Classic Build 需要先登录
  echo_info "检查 Expo 登录状态..."
  if ! npx expo whoami &> /dev/null; then
    echo_warn "未登录 Expo，请运行: npx expo login"
    echo_info "或使用 EAS Build (推荐): ./build-android.sh --eas"
    exit 1
  fi
  
  if [ "$BUILD_TYPE" = "aab" ]; then
    echo_info "构建 Android App Bundle..."
    npx expo build:android -t app-bundle
  else
    echo_info "构建 APK..."
    npx expo build:android -t apk
  fi
  
  if [ $? -eq 0 ]; then
    echo_ok "Expo Build 提交成功！"
    echo_info "构建完成后会收到下载链接"
  else
    echo_error "Expo Build 失败"
    exit 1
  fi
}

# 本地 Android 打包
build_local_android() {
  echo_info "执行本地 Android 打包..."
  
  # 确保 Android 原生项目已生成
  if [ ! -d "android" ]; then
    echo_warn "android/ 目录不存在，正在生成..."
    npx expo prebuild --platform android
  fi
  
  # 执行 Gradle 构建
  cd android
  
  if [ "$BUILD_TYPE" = "aab" ]; then
    echo_info "构建 AAB..."
    ./gradlew bundleRelease
    local artifact_path="app/build/outputs/bundle/release/app-release.aab"
  else
    echo_info "构建 APK..."
    ./gradlew assembleRelease
    local artifact_path="app/build/outputs/apk/release/app-release.apk"
  fi
  
  cd ..
  
  if [ -f "android/${artifact_path}" ]; then
    # 复制到输出目录
    local basename=$(basename "$artifact_path")
    local output_name="tianlian-v3-v${APP_VERSION}-b${BUILD_NUMBER}-${basename}"
    cp "android/${artifact_path}" "${OUTPUT_DIR}/${output_name}"
    echo_ok "打包完成: ${OUTPUT_DIR}/${output_name}"
    echo_ok "文件大小: $(du -h "${OUTPUT_DIR}/${output_name}" | cut -f1)"
  else
    echo_error "本地打包失败，产物未生成"
    exit 1
  fi
}

# 清理构建缓存
clean_build() {
  echo_info "清理构建缓存..."
  rm -rf "${PROJECT_DIR}/dist"
  rm -rf "${PROJECT_DIR}/android/app/build"
  echo_ok "缓存已清理"
}

# ============================================================
# 主流程
# ============================================================

main() {
  print_banner
  
  # 解析参数
  local build_mode="eas"  # 默认使用 EAS
  
  while [[ $# -gt 0 ]]; do
    case $1 in
      --eas)
        build_mode="eas"
        shift
        ;;
      --expo)
        build_mode="expo"
        shift
        ;;
      --local)
        build_mode="local"
        shift
        ;;
      --aab)
        BUILD_TYPE="aab"
        shift
        ;;
      --apk)
        BUILD_TYPE="apk"
        shift
        ;;
      --dev|--development)
        BUILD_PROFILE="development"
        shift
        ;;
      --preview)
        BUILD_PROFILE="preview"
        shift
        ;;
      --prod|--production)
        BUILD_PROFILE="production"
        shift
        ;;
      --clean)
        clean_build
        shift
        ;;
      --version)
        shift
        APP_VERSION="$1"
        shift
        ;;
      --build-number)
        shift
        BUILD_NUMBER="$1"
        shift
        ;;
      --keystore)
        generate_keystore
        exit 0
        ;;
      -h|--help)
        show_help
        exit 0
        ;;
      *)
        echo_error "未知参数: $1"
        show_help
        exit 1
        ;;
    esac
  done
  
  # 检查环境
  check_environment
  
  # 检查文件
  check_files
  
  # 类型检查
  type_check
  
  # 根据模式执行构建
  case $build_mode in
    eas)
      if [ "$EAS_AVAILABLE" = false ]; then
        echo_error "EAS CLI 未安装"
        echo_info "安装 EAS CLI: npm install -g eas-cli"
        echo_info "或使用其他构建方式:"
        echo_info "  --expo   : 使用 Expo Classic Build"
        echo_info "  --local  : 本地打包"
        exit 1
      fi
      build_with_eas
      ;;
    expo)
      build_with_expo
      ;;
    local)
      # 本地打包需要 Android SDK
      if [ -z "$ANDROID_HOME" ] && [ -z "$ANDROID_SDK_ROOT" ]; then
        echo_error "未配置 Android SDK"
        echo_info "请安装 Android Studio 或设置 ANDROID_HOME 环境变量"
        echo_info "或使用其它构建方式 (--eas 或 --expo)"
        exit 1
      fi
      
      # 本地打包需要签名
      if [ "$BUILD_PROFILE" = "production" ]; then
        generate_keystore
        configure_gradle_signing
      fi
      
      build_local_android
      ;;
  esac
  
  echo ""
  echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}║           🎉 打包流程完成! 🎉             ║${NC}"
  echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"
  echo ""
  echo_info "应用名称: 天链运维"
  echo_info "版本号:   v${APP_VERSION} (build ${BUILD_NUMBER})"
  echo_info "包名:     com.tianlian.v3"
  echo ""
  
  if [ "$build_mode" = "local" ]; then
    echo_info "APK 文件位置: ${OUTPUT_DIR}/"
    ls -lh "${OUTPUT_DIR}/tianlian-v3-"* 2>/dev/null
  fi
}

show_help() {
  echo ""
  echo "天链运维 Android APK 打包脚本"
  echo ""
  echo "用法:"
  echo "  ./build-android.sh [选项]"
  echo ""
  echo "构建方式:"
  echo "  --eas        使用 EAS Build (默认，推荐)"
  echo "  --expo       使用 Expo Classic Build"
  echo "  --local      本地打包 (需要 Android SDK)"
  echo ""
  echo "构建产物:"
  echo "  --apk        构建 APK (默认)"
  echo "  --aab        构建 Android App Bundle"
  echo ""
  echo "构建配置:"
  echo "  --dev        开发环境"
  echo "  --preview    预览环境"
  echo "  --prod       生产环境 (默认)"
  echo ""
  echo "其他选项:"
  echo "  --version VER        设置版本号"
  echo "  --build-number NUM   设置构建号"
  echo "  --keystore           生成签名密钥"
  echo "  --clean              清理构建缓存"
  echo "  -h, --help           显示帮助"
  echo ""
  echo "环境变量:"
  echo "  BUILD_TYPE           构建类型 (apk|aab)"
  echo "  BUILD_PROFILE        构建配置 (development|preview|production)"
  echo "  APP_VERSION          应用版本号"
  echo "  BUILD_NUMBER         构建编号"
  echo "  KEYSTORE_PATH        Keystore 路径"
  echo "  KEYSTORE_PASSWORD    Keystore 密码"
  echo "  KEYSTORE_KEY_PASSWORD Key 密码"
  echo ""
  echo "示例:"
  echo "  # EAS 云端打包 (推荐)"
  echo "  ./build-android.sh"
  echo ""
  echo "  # 开发预览版"
  echo "  ./build-android.sh --eas --dev"
  echo ""
  echo "  # 本地打包 APK (需 Android SDK)"
  echo "  ./build-android.sh --local --apk"
  echo ""
  echo "  # 生成签名密钥"
  echo "  ./build-android.sh --keystore"
  echo ""
}

# 执行主流程
main "$@"