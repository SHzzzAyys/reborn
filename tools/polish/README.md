# Reborn 润色助手

本地 Web 工具：选一篇 Markdown 章节 → AI 逐段润色 → 你逐段决定接受/拒绝/跳过 → 一键保存回原文件。

调用 [DeepSeek API](https://platform.deepseek.com/) `deepseek-chat` 模型，中文润色质量好且便宜。

## 准备

```bash
cd tools/polish
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，把 DEEPSEEK_API_KEY 换成你的真实 key
```

## 运行

```bash
uvicorn server:app --reload --port 8000
```

浏览器打开 http://localhost:8000

## 使用

1. 顶部下拉框选一个 `.md` 文件（如 `A01.md`）
2. 每个正文段落是一张白色卡片，灰色卡片是不会被改动的标题/代码/图片/空行
3. 点「润色这段」或顶部「润色全部段落」
4. AI 给出修改后，原文与建议会用绿色（新增）/红色（删除）高亮 diff 显示
5. 选 **接受 / 拒绝 / 重新润色 / 跳过**
6. 全部审完后点 **保存到文件**
   - 保存前会自动备份原文件到 `.backups/<name>.<时间戳>.bak`
   - 如果文件在外部被改动，保存会拒绝并提示重新加载

## 安全

- `.env` 与 `.backups/` 已加入 `.gitignore`
- 后端只读写仓库根目录下的 `.md` 文件，不允许路径穿越
- 保存时会校验"非正文块"（标题、代码、图片、空行）必须一字不差，避免误改

## 文件结构

```
tools/polish/
├── server.py            # FastAPI 后端
├── deepseek_client.py   # DeepSeek API 封装
├── md_splitter.py       # Markdown 段落切分（保留代码块/标题/图片不动）
├── static/
│   ├── index.html
│   └── app.js
├── requirements.txt
├── .env.example
└── README.md
```
