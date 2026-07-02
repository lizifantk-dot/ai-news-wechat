# AI News WeChat Brief

每天用 GitHub Actions 抓取全球 AI 动态，并通过 Server 酱推送到微信。

## 功能

- 每天曼谷时间 09:00 自动运行
- 支持手动运行
- Server 酱微信推送
- 默认不需要付费模型，直接聚合 RSS 新闻
- 可选配置 OpenAI API Key，生成更高质量的中文电商运营简报

## GitHub Public 仓库设置

1. 在 GitHub 新建一个 Public repository。
2. 把本目录 `ai-news-wechat` 里的文件上传到仓库根目录。
3. 打开仓库 `Settings` -> `Secrets and variables` -> `Actions`。
4. 新增 Repository secret：
   - Name: `SERVERCHAN_SENDKEY`
   - Value: 你的 Server 酱 SendKey
5. 可选：如果你希望简报更像人工整理，而不是新闻聚合，再新增：
   - Name: `OPENAI_API_KEY`
   - Value: 你的 OpenAI API Key
6. 打开 `Actions` 页面，选择 `Daily AI Brief to WeChat`，点击 `Run workflow` 测试。

## 费用说明

- Public 仓库使用标准 GitHub-hosted runner 通常不消耗你的 Actions 计费额度。
- Server 酱免费版通常足够每天一次推送。
- 不配置 `OPENAI_API_KEY` 时，不会产生 OpenAI API 费用。
- 配置 `OPENAI_API_KEY` 后，会按 OpenAI API 用量计费。

## 调整推送时间

当前配置在 `.github/workflows/daily-ai-brief.yml`：

```yaml
- cron: "0 2 * * *"
```

GitHub Actions 使用 UTC 时间。曼谷时间 09:00 等于 UTC 02:00。

## 新闻源

新闻源配置在 `scripts/daily_ai_brief.py` 的 `FEEDS` 列表里，可以自行增删。
