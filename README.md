# SKBro

> Your local AI skill manager.

`SKBro` 是一个本地优先、零服务依赖的 AI Skill 管理工具，用来创建、安装、搜索、使用、更新和分享 Skill。

## 特点

- 支持完整 Skill 目录和单个 Markdown 文件；
- 支持本地目录、ZIP、HTTP URL 和 Git 仓库；
- 支持软链接和复制两种项目使用方式；
- 内置 Codex、Claude 和通用项目目录；
- 可以把 Skill 打包成 ZIP 分享；
- 本地 JSON 存储，无账号、数据库或后台服务；
- 核心只使用 Python 标准库。

## 安装

需要 Python 3.10 或更高版本。

### PyPI 安装

正式发布到 PyPI 后，推荐使用：

```bash
pipx install skbro
```

或：

```bash
uv tool install skbro
```

### 从 GitHub 安装

```bash
pipx install "git+https://github.com/AuCf/skbro.git"
```

### 从本地源码安装

```bash
git clone https://github.com/AuCf/skbro.git
cd skbro
pipx install .
```

开发时也可以直接运行：

```bash
python -m skbro --help
```

验证安装：

```bash
skbro --version
skbro --help
```

更新或卸载：

```bash
pipx upgrade skbro
pipx uninstall skbro
```

## 最快上手

创建一个 Skill：

```bash
skbro create api-reviewer \
  --description "Review API designs" \
  --tags api,review
```

生成：

```text
api-reviewer/
├── SKILL.md
└── skill.json
```

安装并用于当前项目：

```bash
skbro add ./api-reviewer
skbro use api-reviewer
```

默认位置：

```text
.skills/api-reviewer/
```

用于 Codex 或 Claude：

```bash
skbro use api-reviewer --target codex
skbro use api-reviewer --target claude
```

## 安装别人分享的 Skill

```bash
# 本地目录或 Markdown
skbro add ./my-skill
skbro add ./my-skill.md --name my-skill

# ZIP
skbro add ./my-skill-1.0.0.zip

# HTTP URL
skbro add https://example.com/my-skill-1.0.0.zip

# Git
skbro add https://github.com/example/my-skill.git
skbro add https://github.com/example/my-skill.git --ref v1.0.0
```

## 日常管理

```bash
skbro list
skbro search API
skbro info api-reviewer
skbro status
skbro update api-reviewer
skbro unuse api-reviewer
skbro remove api-reviewer
skbro doctor
```

不指定名称时，`skbro update` 会更新所有有来源记录的 Skill。

## 软链接与复制模式

默认使用软链接。中央 Skill 更新后，项目立即生效：

```bash
skbro update api-reviewer
```

Windows 无法创建软链接，或希望项目保留完整副本时：

```bash
skbro use api-reviewer --copy
```

复制模式更新后需要同步：

```bash
skbro status
skbro sync api-reviewer
```

如果项目副本被人工修改，`sync` 和 `unuse` 会拒绝覆盖或删除；确认放弃修改时使用 `--force`。

## 分享 Skill

```bash
skbro pack api-reviewer
```

会生成：

```text
api-reviewer-0.1.0.zip
```

对方安装：

```bash
skbro add ./api-reviewer-0.1.0.zip
```

也可以把 Skill 目录放进独立 Git 仓库分享。

## Skill 格式

最小格式：

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

```bash
skbro config
skbro config set link_mode copy
skbro config set default_target codex
skbro config set target.cursor .cursor/skills
```

默认数据目录：

```text
~/.skbro/
├── config.json
├── registry.json
└── skills/
```

测试或多环境使用时，可设置 `SKBRO_HOME`。

## 旧版兼容

- `skm` 命令继续作为兼容别名；
- `SKM_HOME` 环境变量继续可用；
- 已存在 `~/.skill_manager` 时会继续使用，不会丢失原数据；
- `register/link/unlink` 旧命令继续可用；
- 旧版单 Markdown registry 可以继续读取。

## 开发验证

```bash
python -B -m unittest discover -s tests -v
```

测试覆盖本地生命周期、旧版兼容、Markdown 转换、ZIP/HTTP/Git 安装、更新同步、修改保护、路径安全和健康检查。
