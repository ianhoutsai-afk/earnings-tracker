# 📈 Magnificent Seven Earnings Tracker

这是一个基于 GitHub Actions 的自动化财报追踪系统。它会自动抓取美股七巨头 (Mag 7) 的预计发布日期和历史财报，并通过 GitHub Pages 实时展示在网页上。

## ✨ 特点
- **全自动更新**：每小时自动同步一次数据，无需手动干预。
- **本地化时间**：自动识别用户时区，显示最精准的更新时间。
- **一键部署**：通过 GitHub 模板，无需安装 Python 环境即可部署。
- **快速访问**：直接集成 SEC 官方链接，支持手机/电脑快捷跳转。

## 🚀 快速部署指南 (3分钟完成)

### 第一步：创建自己的仓库
1. 点击页面上方的 **`Use this template`** $\to$ **`Create a new repository`**。
2. 为你的新仓库起个名字（例如 `my-earnings-tracker`），设置为 `Public`。
3. 点击 **`Create repository from template`**。

### 第二步：开启自动化权限
为了让 GitHub Actions 能自动更新数据，你需要开启写入权限：
1. 进入你的新仓库 $\to$ **`Settings`** (右上角)。
2. 点击左侧菜单的 **`Actions`** $\to$ **`General`**。
3. 滚动到最下方 **`Workflow permissions`** $\to$ 选择 **`Read and write permissions`** $\to$ 点击 **`Save`**。

### 第三步：开启网页展示 (GitHub Pages)
1. 进入 **`Settings`** $\to$ 点击左侧菜单的 **`Pages`**。
2. 在 **`Build and deployment`** $\to$ **`Branch`** 中选择 `main` 分支 $\to$ 点击 **`Save`**。
3. 等待 1-2 分钟，你会在页面上方看到你的网站地址 (例如 `https://yourname.github.io/my-earnings-tracker/`)。

---

## 🛠️ 工作原理
- **数据源**：使用 `yfinance` 获取预计日期 $\to$ `SEC.gov` 获取历史财报。
- **自动化**：`.github/workflows/main.yml` 每小时触发一次 Python 脚本。
- **存储**：更新后的数据保存在 `data.json` 中。
- **前端**：`index.html` 实时读取 JSON 并通过 Tailwind CSS 渲染。# earnings-tracker
