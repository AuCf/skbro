# Skill Manager 设计说明

## 产品原则

1. 本地优先：用户拥有 Skill 文件和索引数据；
2. 分享简单：目录、ZIP 和 Git 都可以作为分享载体；
3. 使用简单：核心流程保持为 `add → use → update → pack`；
4. 安全默认：项目目标不能越出项目目录，压缩包不能路径穿越；
5. 兼容渐进：旧版单 Markdown 和命令继续工作；
6. 核心零依赖：只依赖 Python 标准库，Git 来源使用系统 Git。

## 数据目录

```text
~/.skill_manager/
├── config.json
├── registry.json
├── skills/
│   └── <name>/
│       ├── SKILL.md
│       └── skill.json
└── registry/              # 旧版兼容目录
```

`registry.json` 是已安装 Skill、来源和项目使用关系的索引。Skill 内容仍以普通文件目录保存，用户可以检查、备份和迁移。

## 来源模型

每个 Skill 记录一个来源：

- `local`：本地 Markdown 或目录；
- `zip`：本地 ZIP；
- `url`：HTTP Markdown 或 ZIP；
- `git`：Git 仓库，可记录分支或标签。

`skm update` 会重新读取来源并原子替换中央 Skill。项目使用软链接时会立即看到新内容；复制模式通过 `skm status` 和 `skm sync` 更新。

## 项目目标

默认配置提供：

| 名称 | 目录 |
|---|---|
| `default` | `.skills` |
| `codex` | `.codex/skills` |
| `claude` | `.claude/skills` |

目标目录必须是项目内相对路径。用户可以通过 `skm config set target.<name> <path>` 添加目标。

## 安全边界

- registry 中的 Skill 路径必须位于 `SKM_HOME`；
- 项目目标必须位于当前项目；
- ZIP 导入拒绝绝对路径、`..` 和符号链接；
- Skill 目录导入拒绝符号链接，确保分享包可移植；
- JSON 使用同目录临时文件、刷新磁盘并通过 `os.replace` 替换；
- `remove` 在 Skill 仍被项目使用时拒绝删除；
- `doctor --repair` 只自动清理缺失的链接记录，不删除孤立 Skill 数据。

## 模块职责

```text
skm/cli.py          命令解析和输出
skm/models.py       Skill manifest 模型与校验
skm/storage.py      配置、registry 和安全路径
skm/sources.py      本地、ZIP、HTTP 和 Git 来源
skm/skill_ops.py    创建、安装、更新和删除
skm/project_ops.py  项目使用、状态和同步
skm/sharing.py      ZIP 打包
skm/doctor.py       健康检查与安全修复
```

## 后续演进边界

中心市场、账号系统、团队权限、Web UI 和云同步不属于本地核心。未来如需增加，应作为可选服务，不能成为本地创建、安装、使用和分享 Skill 的前置条件。
