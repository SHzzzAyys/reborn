# Reborn 章节 Lint 工具

只读 Markdown 质量检查器：扫描仓库根目录下所有 `.md` 文件，输出问题清单。**绝不修改原文。**

## 用法

```bash
# 扫描全仓库
python tools/lint/check.py

# 同时生成 HTML 报告 → tools/lint/report.html
python tools/lint/check.py --html

# 只跑某条规则
python tools/lint/check.py --rule duplicate-char

# 只看汇总数
python tools/lint/check.py --quiet
```

退出码：发现 `error` 级别问题返回 1，其他返回 0（方便挂 pre-commit）。

## 规则

| ID | 级别 | 检查 |
|---|---|---|
| `broken-image` | error | `![](images/X)` 但 `images/X` 不存在 |
| `broken-footnote-ref` | error | `[^N]` 引用了但同文件无 `[^N]:` 定义 |
| `unused-footnote-def` | warn | `[^N]:` 定义了但同文件无引用 |
| `duplicate-char` | warn | 中文叠字（"的的"、"在在"、"是是"、"了了"、"吗吗"、"呢呢"、"啊啊"） |
| `mixed-cn-en-punct` | warn | 同行混用中英文句号或逗号 |
| `trailing-whitespace` | warn | 非空行末尾有空格/Tab |
| `multiple-blank-lines` | warn | 3 个或更多连续空行 |

### 误报处理

`duplicate-char` 已内置上下文白名单：
- `"是是"` 后跟 `否` / `非` 不报警（"是是否" "是是非" 是合法中文）
- `"了了"` 前面是 `为` 不报警（"为了了解" 合法）

`mixed-cn-en-punct` 跳过：
- 含反引号的行（代码片段）
- 含 URL 的行
- 没有任何 CJK 字符的纯英文行

如果还有误报，可以用 `--rule <id>` 单独跑、或在该行末尾改写规避，工具不会强制修改原文。

## 与 polish 工具的关系

```
原稿 ──▶  lint  ──▶ 修硬错误（脚注/图片/叠字）
              │
              ▼
         polish ──▶ 润色不通顺的句子
              │
              ▼
            最终稿
```

先 lint 后 polish 效率最高 — 先把 LLM 看不见的硬错误手工修掉。

## 不会做的事

- ❌ 自动修复（违反"只读"原则）
- ❌ 改写章节文件
- ❌ 调用任何外部 API（纯本地 stdlib）

## 实现

单文件 `check.py`，纯 Python stdlib 零依赖。每条规则一个 `check_*(file, lines) -> List[Issue]` 函数，主流程聚合后排序输出。
