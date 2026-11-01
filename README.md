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
