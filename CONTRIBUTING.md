# 贡献指南

感谢你愿意帮助改进 Daily。

## 开始之前

1. 先搜索已有 Issue。
2. 较大的功能先开 Discussion 或 Issue 说明使用场景和边界。
3. 不要提交真实日记、画像、数据库、API Key、服务器地址或未经审核的截图。

## 本地检查

```bash
cd backend
python -m unittest discover -s tests

cd ../frontend
npm ci
npm run build
```

## Pull Request

- 一次 PR 只解决一个主题。
- 写清楚行为变化、验证方式和隐私影响。
- UI 变化附脱敏截图。
- 新增 AI 写操作时必须保留显式确认，失败时默认不写入。
- 新增周期总结数据时必须标明数据来源，禁止在无记录时编造事实。

贡献代码即表示你同意按项目的 AGPL-3.0 许可证发布。
