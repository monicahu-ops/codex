# 工作记录

一个本地运行的 Flask + SQLite 网页应用，提供：

- 工作日志：按日期、标签记录进展与复盘；支持编辑、删除。
- 工作待办：可由一篇工作日志一键生成，并标记完成。
- 工作月报、年报：基于对应时间范围的日志和待办实时汇总，不额外保存重复数据。

## 启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

然后访问 http://127.0.0.1:5000 。首次启动会在项目目录创建 `worklog.db`。

macOS 用户也可以双击“启动工作记录.command”启动；不要直接打开 `templates/index.html`，因为它需要后端提供数据。

## 使用与备份

日志和待办默认查询当年；待办默认同时显示未设置截止日期的事项。重置查询会恢复这组默认条件。月报和年报按项目展示记录和可编辑的项目总结，导出及复制使用最后保存的总结。

程序每天首次启动时在 `backups/` 自动备份数据库，保留最近 30 份自动备份。也可以从“备份与恢复”下载备份；恢复前会在同一目录保存当前数据。建议定期将手动备份另存到其他设备或可信位置。备份不包含 AI 密钥。

## AI 总结

在“AI 配置说明”中按需填写 OpenAI API 密钥和模型。密钥保存在项目目录的 `.ai-config.json`，被 Git 忽略；也可以使用 `OPENAI_API_KEY` 和 `OPENAI_MODEL` 环境变量。只有点击“生成 AI 初稿”并确认后，才会发送对应项目和时间段内的日志。初稿需要检查并手动保存。使用 API 可能产生服务费用。

## 测试

```bash
.venv/bin/python -m unittest -v test_app
```
