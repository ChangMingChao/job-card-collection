# 部署成可分享网站

这个目录已经是一个独立静态网站。核心文件：

- `index.html`：网站页面
- `jobs-data.js`：岗位数据
- `jobs.csv`：岗位表格备份
- `extract_jobs.py`：从腾讯文档刷新数据
- `.github/workflows/deploy.yml`：GitHub Pages 自动部署和每日刷新

## 推荐方式：GitHub Pages

1. 新建一个 GitHub 仓库。
2. 把 `job-card-collection` 目录里的所有文件上传到仓库根目录。
3. 进入仓库 `Settings` → `Pages`。
4. 在 `Build and deployment` 里选择 `GitHub Actions`。
5. 打开 `Actions`，运行 `Update and deploy job board`。
6. 部署完成后，GitHub 会给你一个公开网址，可以分享给其他人。

## 每日自动更新

工作流会每天 UTC 01:00 自动运行一次，也就是北京时间 09:00。它会：

1. 重新抓取腾讯文档。
2. 生成新的 `jobs-data.js` 和 `jobs.csv`。
3. 自动发布最新网页。

也可以在 GitHub Actions 页面手动点击 `Run workflow` 立即更新。

## 其他平台

如果只想快速分享，也可以把 `index.html`、`jobs-data.js`、`jobs.csv` 上传到 Netlify、Vercel、Cloudflare Pages 或任意静态托管服务。只是这些平台不会自动运行 `extract_jobs.py`，除非你额外配置定时构建。
