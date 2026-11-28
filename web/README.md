# GradeManager 前端

在 `web/` 下安装依赖并启动开发服务器：

```sh
npm ci
npm run dev
```

开发服务器将 `/api` 请求转发到 `127.0.0.1:8000`，需要同时启动 FastAPI 后端。
运行 `npm run build` 进行类型检查并构建到 `web/dist/`。

推送前端变更到 `main` 时，GitHub Actions 会运行同样的构建。可在 Actions 的「Build web」运行页面下载 `web-dist` 产物，也可手动触发构建。
