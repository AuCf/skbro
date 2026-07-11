# Skill Manager (`skm`)

`skm` 是一个本地优先、零服务依赖的 AI Skill 管理工具。

它解决一件事：把散落在电脑和项目里的 Skill 统一管理，并能简单地安装、使用、更新和分享。

## 特点

- 支持完整 Skill 目录，也兼容单个 Markdown 文件；
- 支持本地目录、ZIP、HTTP URL 和 Git 仓库；
- 支持软链接和复制两种项目使用方式；
- 内置 Codex、Claude 和通用项目目录；
- Skill 可打包成 ZIP 直接分享；
- 本地 JSON 存储，无账号、数据库或后台服务；
- 只使用 Python 标准库。

## 安装

需要 Python 3.10 或更高版本。

在项目目录开发运行：

```bash
python -m skm --help
```

安装为独立命令：

```bash
pipx install git+https://github.com/AuCf/skill-manager.git
```

也可以使用 `uv`：

```bash
uv tool install git+https://github.com/AuCf/skill-manager.git
```

从本地源码安装时，把地址换成项目目录或 `.` 即可。

## 最快上手

创建一个 Skill：

```bash
skm create api-reviewer \
  --description "Review API designs" \
  --tags api,review
```

生成的目录：

```text
api-reviewer/
├── SKILL.md
└── skill.json
```

安装并在当前项目使用：

```bash
skm add ./api-reviewer
skm use api-reviewer
```

默认会出现在：

```text
.skills/api-reviewer/
```

使用到 Codex 或 Claude 的项目目录：

```bash
skm use api-reviewer --target codex
skm use api-reviewer --target claude
```

## 安装别人分享的 Skill

本地目录或 Markdown：

```bash
skm add ./my-skill
skm add ./my-skill.md --name my-skill
```

ZIP 包：

```bash
skm add ./my-skill-1.0.0.zip
```

HTTP URL：

```bash
skm add https://example.com/my-skill-1.0.0.zip
```

Git 仓库：

```bash
skm add https://github.com/example/my-skill.git
skm add https://github.com/example/my-skill.git --ref v1.0.0
```

Git 仓库根目录需要包含 `SKILL.md`，推荐同时包含 `skill.json`。

## 日常管理

```bash
skm list
skm search API
skm info api-reviewer
skm status
skm update api-reviewer
skm unuse api-reviewer
skm remove api-reviewer
skm doctor
```

不指定名称时，`skm update` 会更新所有有来源记录的 Skill。

### 复制模式

Windows 无法创建软链接，或希望项目包含完整副本时：

```bash
skm use api-reviewer --copy
```

中央 Skill 更新后，`status` 会把旧副本显示为 `outdated`：

```bash
skm status
skm sync api-reviewer
```

## 分享 Skill

打包已安装的 Skill：

```bash
skm pack api-reviewer
```

输出文件示例：

```text
api-reviewer-0.1.0.zip
```

把 ZIP 发给别人，对方执行：

```bash
skm add ./api-reviewer-0.1.0.zip
```

也可以把 Skill 目录放到独立 Git 仓库中直接分享。

## Skill 格式

最小格式只有一个入口文件：

```text
my-skill/
└── SKILL.md
```

推荐格式：

```text
my-skill/
├── SKILL.md
├── skill.json
├── scripts/
├── references/
└── assets/
```

`skill.json` 示例：

```json
{
  "schema_version": 1,
  "name": "api-reviewer",
  "version": "1.0.0",
  "description": "Review API designs",
  "note": "用于检查接口一致性、安全性和可维护性",
  "tags": ["api", "review"],
  "author": "Your Name",
  "license": "MIT",
  "entry": "SKILL.md"
}
```

## 配置

查看配置：

```bash
skm config
```

修改默认关联方式：

```bash
skm config set link_mode copy
```

修改默认目标：

```bash
skm config set default_target codex
```

增加自定义项目目录：

```bash
skm config set target.cursor .cursor/skills
skm use api-reviewer --target cursor
```

默认数据目录：

```text
~/.skill_manager/
├── config.json
├── registry.json
└── skills/
```

测试或多环境使用时，可设置 `SKM_HOME`。

## 旧版兼容

原有命令仍然可用：

```bash
skm register ./skill.md --name skill-name
skm link skill-name
skm unlink skill-name
```

旧版 `registry/<name>.md` 数据也可以继续读取和取消关联。

## 开发验证

运行测试：

```bash
python -B -m unittest discover -s tests -v
```

当前测试覆盖本地生命周期、Markdown 转换、ZIP/HTTP/Git 安装、更新同步、路径安全和健康检查。
