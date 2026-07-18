# teacher 前端

教师端已切换为 Vue 3 + Vite 结构，当前目录为独立子应用。

## 主要能力

- 课件上传、删除、发布
- 讲稿查看、编辑、AI 生成
- 学情统计、提问记录、卡点分析

## 开发说明

- 默认接口基址见 [src/config/api.js](src/config/api.js)
- 统一接口走 `/api/v1/...`
- 课件预览仍使用 `/api/courseware/:courseId/page/:pageNum`

## 常用命令

- `npm install`
- `npm run dev`
- `npm run build`
