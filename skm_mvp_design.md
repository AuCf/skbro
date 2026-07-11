# Skill Manager MVP 设计文档

> 历史文档：项目现已更名为 `SKBro`。当前设计和命令请以 `README.md` 与 `DESIGN.md` 为准。

> 项目代号：`skm`  
> 全称：Skill Manager  
> 定位：一个本地极简 CLI 工具，用于统一管理、搜索、注册和关联 AI Skill 文件。

---

## 1. 背景

在多个项目中使用 AI 编程工具时，常常会沉淀大量可复用的 Skill，例如：

- Git commit 规范生成
- API 代码生成
- 前端组件生成
- PRD 生成
- 数据库表结构生成

如果这些 Skill 分散存放在不同项目中，会出现几个问题：

1. Skill 难以复用；
2. 多个项目重复复制，维护成本高；
3. 不知道某个 Skill 被哪些项目使用过；
4. Skill 数量多了以后，缺少搜索和分类能力；
5. 英文文件名不够直观，需要中文备注辅助管理。

因此，需要一个轻量级本地 CLI 工具，用来统一管理 Skill。

---

## 2. MVP 目标

MVP 阶段只解决最核心的问题：

> 把分散在不同项目中的 Skill 文件统一登记到本地仓库，并能一键关联到当前项目。

核心目标：

1. 支持将一个 `.md` Skill 文件注册到中央 Skill 仓库；
2. 注册时支持填写英文名称、标签、描述和中文备注；
3. 支持在任意项目目录下把某个 Skill 软链接到当前项目；
4. 支持查看所有 Skill；
5. 支持搜索 Skill，搜索范围包含名称、标签、描述、中文备注；
6. 支持取消当前项目和某个 Skill 的关联。

---

## 3. 非目标

MVP 阶段暂不做以下功能：

1. 不做云同步；
2. 不做 Web UI；
3. 不做团队权限管理；
4. 不做 Skill 版本管理；
5. 不做远程 Skill 市场；
6. 不做复杂依赖管理；
7. 不做数据库，优先使用本地 JSON 文件。

这些能力可以放到后续版本扩展。

---

## 4. 核心概念

### 4.1 Skill

Skill 是一个 Markdown 文件，通常用于描述某类可复用的 AI 工作能力。

示例：

```text
api-generator.md
git-commit.md
coat-style-research.md
prd-writer.md
```

### 4.2 Registry

Registry 是本地 Skill 中央仓库，用来存放所有已登记的 Skill 源文件。

### 4.3 Project Link

Project Link 是指把中央仓库中的某个 Skill 关联到当前项目。

默认通过软链接实现。

---

## 5. 本地目录结构

所有数据统一存放在用户主目录下：

```bash
~/.skill_manager/
├── config.json
├── registry.json
└── registry/
    ├── api-generator.md
    ├── git-commit.md
    └── coat-style-research.md
```

说明：

- `config.json`：全局配置文件；
- `registry.json`：Skill 索引文件；
- `registry/`：存放所有 Skill 源文件。

---

## 6. 项目内目录结构

当用户在某个项目中执行 `skm link` 时，默认会在当前项目下创建 `.skills/` 目录。

示例：

```bash
your-project/
├── src/
├── package.json
└── .skills/
    └── api-generator.md -> ~/.skill_manager/registry/api-generator.md
```

默认项目内 Skill 目录：

```bash
.skills/
```

后续可以通过配置改成：

```bash
.claude/skills/
.cursor/skills/
.codex/skills/
```

---

## 7. 配置文件设计

文件路径：

```bash
~/.skill_manager/config.json
```

示例：

```json
{
  "project_skill_dir": ".skills",
  "link_mode": "symlink"
}
```

字段说明：

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `project_skill_dir` | string | `.skills` | 当前项目中存放 Skill 链接的目录 |
| `link_mode` | string | `symlink` | Skill 关联方式，MVP 默认使用软链接 |

`link_mode` MVP 阶段支持：

```text
symlink
copy
```

说明：

- `symlink`：默认方式，创建软链接；
- `copy`：复制文件，适合 Windows 或软链接失败的场景。

---

## 8. Registry 数据结构

文件路径：

```bash
~/.skill_manager/registry.json
```

示例：

```json
{
  "skills": {
    "api-generator": {
      "name": "api-generator",
      "file": "registry/api-generator.md",
      "description": "Generate API code from API specification.",
      "note": "根据接口文档自动生成后端 API 代码，适合 FastAPI、Node.js 和直播电商后台项目。",
      "tags": ["api", "backend", "generator"],
      "linked_projects": [
        "/Users/ava/projects/order-system",
        "/Users/ava/projects/live-commerce-tool"
      ],
      "created_at": "2026-06-30T10:00:00+09:00",
      "updated_at": "2026-06-30T10:00:00+09:00"
    }
  }
}
```

字段说明：

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `name` | string | 是 | Skill 唯一名称，建议英文短横线命名 |
| `file` | string | 是 | Skill 源文件在 `~/.skill_manager/` 下的相对路径 |
| `description` | string | 否 | 英文或短描述，便于程序展示 |
| `note` | string | 否 | 中文备注，便于人理解和搜索 |
| `tags` | array | 否 | 标签列表 |
| `linked_projects` | array | 是 | 已关联该 Skill 的项目路径 |
| `created_at` | string | 是 | 创建时间 |
| `updated_at` | string | 是 | 更新时间 |

---

## 9. 命令设计

MVP 阶段支持以下命令：

```bash
skm init
skm list
skm register
skm link
skm unlink
skm search
skm info
```

---

## 10. 命令详情

### 10.1 初始化

```bash
skm init
```

作用：

初始化本地 Skill Manager 目录。

执行后创建：

```bash
~/.skill_manager/
├── config.json
├── registry.json
└── registry/
```

如果目录已经存在，则不重复覆盖。

---

### 10.2 查看所有 Skill

```bash
skm list
```

作用：

查看当前已登记的所有 Skill。

示例输出：

```text
NAME                 TAGS               LINKED   NOTE
api-generator        api,backend        yes      根据接口文档自动生成后端 API 代码
git-commit           git,workflow       no       自动生成规范化 commit message
coat-research        fashion,research   yes      毛呢大衣款式调研与爆款分析
```

说明：

- `LINKED` 表示该 Skill 是否已经关联到当前项目；
- `NOTE` 显示中文备注；
- 如果中文备注太长，可以截断展示。

---

### 10.3 注册 Skill

```bash
skm register ./my-skill.md \
  --name api-generator \
  --tags api,backend \
  --description "Generate API code from API specification." \
  --note "根据接口文档自动生成后端 API 代码，适合 FastAPI、Node.js 和直播电商后台项目。"
```

作用：

把一个本地 `.md` 文件登记到中央 Skill 仓库。

执行逻辑：

1. 校验源文件是否存在；
2. 校验文件是否为 `.md`；
3. 校验 `name` 是否已经存在；
4. 将文件复制到 `~/.skill_manager/registry/`；
5. 在 `registry.json` 中写入元数据；
6. 写入中文备注 `note`；
7. 返回注册成功信息。

注册后的文件路径示例：

```bash
~/.skill_manager/registry/api-generator.md
```

注册成功输出：

```text
Skill registered successfully.

Name: api-generator
File: ~/.skill_manager/registry/api-generator.md
Note: 根据接口文档自动生成后端 API 代码，适合 FastAPI、Node.js 和直播电商后台项目。
```

---

### 10.4 关联 Skill 到当前项目

```bash
skm link api-generator
```

作用：

把已登记的 Skill 关联到当前项目。

默认执行结果：

```bash
current-project/
└── .skills/
    └── api-generator.md -> ~/.skill_manager/registry/api-generator.md
```

执行逻辑：

1. 读取 `registry.json`；
2. 查找 `api-generator`；
3. 创建当前项目下的 `.skills/` 目录；
4. 创建软链接；
5. 将当前项目绝对路径写入该 Skill 的 `linked_projects`；
6. 更新 `updated_at`。

成功输出：

```text
Skill linked successfully.

Skill: api-generator
Project: /Users/ava/projects/order-system
Target: .skills/api-generator.md
```

---

### 10.5 取消关联

```bash
skm unlink api-generator
```

作用：

取消当前项目和某个 Skill 的关联。

执行逻辑：

1. 删除当前项目中的 `.skills/api-generator.md`；
2. 从该 Skill 的 `linked_projects` 中移除当前项目路径；
3. 更新 `registry.json`。

成功输出：

```text
Skill unlinked successfully.

Skill: api-generator
Project: /Users/ava/projects/order-system
```

---

### 10.6 搜索 Skill

```bash
skm search api
```

也可以搜索中文：

```bash
skm search 直播
```

作用：

根据关键词搜索 Skill。

搜索范围：

```text
name
description
note
tags
linked_projects
```

示例输出：

```text
Found 2 skills:

1. api-generator
   Tags: api, backend, generator
   Note: 根据接口文档自动生成后端 API 代码，适合 FastAPI、Node.js 和直播电商后台项目。

2. live-commerce-prd
   Tags: prd, live-commerce
   Note: 用于生成直播电商工具类产品 PRD。
```

---

### 10.7 查看 Skill 详情

```bash
skm info api-generator
```

作用：

查看某个 Skill 的完整信息。

示例输出：

```text
Name: api-generator
Description: Generate API code from API specification.
Note: 根据接口文档自动生成后端 API 代码，适合 FastAPI、Node.js 和直播电商后台项目。
Tags: api, backend, generator
File: ~/.skill_manager/registry/api-generator.md

Linked Projects:
- /Users/ava/projects/order-system
- /Users/ava/projects/live-commerce-tool

Created At: 2026-06-30T10:00:00+09:00
Updated At: 2026-06-30T10:00:00+09:00
```

---

## 11. 中文备注设计

中文备注字段使用：

```json
"note": "中文备注内容"
```

设计原则：

1. `name` 用于命令调用，建议英文；
2. `description` 用于短描述，可以英文；
3. `note` 用于中文解释，方便自己理解；
4. `search` 必须支持中文备注搜索；
5. `list` 默认展示中文备注；
6. `info` 展示完整中文备注。

示例：

```bash
skm register ./coat-research.md \
  --name coat-research \
  --tags fashion,coat,research \
  --description "Research wool coat styles." \
  --note "毛呢大衣款式调研 Skill，用于分析国内外平台爆款、版型、面料、领型和可打样方向。"
```

---

## 12. 文件写入安全策略

MVP 阶段不做复杂并发控制，但写入 `registry.json` 时需要避免直接覆盖。

推荐写入流程：

1. 读取 `registry.json`；
2. 修改内存对象；
3. 写入临时文件 `registry.json.tmp`；
4. 校验 JSON 可解析；
5. 使用 rename 替换原文件。

这样可以降低写坏索引文件的风险。

---

## 13. 软链接失败处理

默认使用软链接：

```bash
ln -s ~/.skill_manager/registry/api-generator.md .skills/api-generator.md
```

如果软链接失败，可以提示用户：

```text
Failed to create symlink.

You can try:
skm link api-generator --copy
```

MVP 可以支持：

```bash
skm link api-generator --copy
```

执行后复制文件到当前项目：

```bash
current-project/
└── .skills/
    └── api-generator.md
```

说明：

- 软链接模式适合统一维护；
- copy 模式适合 Windows 或不允许创建软链接的环境；
- copy 模式下，中央 Skill 更新后，项目内副本不会自动更新。

---

## 14. 错误处理

### 14.1 Skill 名称已存在

```text
Skill already exists: api-generator
```

### 14.2 源文件不存在

```text
File not found: ./my-skill.md
```

### 14.3 文件不是 Markdown

```text
Only .md files can be registered.
```

### 14.4 Skill 不存在

```text
Skill not found: api-generator
```

### 14.5 当前项目已关联

```text
Skill already linked to current project: api-generator
```

### 14.6 当前项目未关联

```text
Skill is not linked to current project: api-generator
```

---

## 15. MVP 验收标准

### 15.1 初始化验收

执行：

```bash
skm init
```

应成功创建：

```bash
~/.skill_manager/config.json
~/.skill_manager/registry.json
~/.skill_manager/registry/
```

---

### 15.2 注册验收

执行：

```bash
skm register ./api-generator.md \
  --name api-generator \
  --tags api,backend \
  --note "根据接口文档自动生成后端 API 代码"
```

应满足：

1. 文件被复制到 `~/.skill_manager/registry/api-generator.md`；
2. `registry.json` 中出现 `api-generator`；
3. `note` 字段保存中文备注；
4. `tags` 被正确解析为数组。

---

### 15.3 关联验收

在项目目录执行：

```bash
skm link api-generator
```

应满足：

1. 当前项目出现 `.skills/api-generator.md`；
2. 默认情况下它是一个软链接；
3. `registry.json` 中该 Skill 的 `linked_projects` 包含当前项目路径。

---

### 15.4 取消关联验收

执行：

```bash
skm unlink api-generator
```

应满足：

1. 当前项目中的 `.skills/api-generator.md` 被删除；
2. `registry.json` 中该 Skill 的 `linked_projects` 移除当前项目路径。

---

### 15.5 搜索验收

执行：

```bash
skm search 接口文档
```

应能搜索到中文备注中包含该关键词的 Skill。

---

## 16. 推荐实现技术

语言：

```text
Python 3.10+
```

推荐标准库：

```text
argparse
json
pathlib
shutil
datetime
os
```

MVP 阶段尽量不引入第三方依赖。

如果想让表格更漂亮，后续可以引入：

```text
rich
typer
```

但第一版不是必须。

---

## 17. MVP 实现优先级

### P0：必须实现

```text
skm init
skm register
skm list
skm link
skm unlink
skm search
中文 note 字段
```

### P1：建议实现

```text
skm info
--copy 模式
registry.json 安全写入
```

### P2：后续实现

```text
skm doctor
skm remove
skm rename
Skill 版本管理
远程同步
团队共享
Web UI
```

---

## 18. 后续版本方向

### 18.1 Skill 健康检查

增加：

```bash
skm doctor
```

检查：

1. `registry.json` 是否可解析；
2. Skill 源文件是否存在；
3. 项目软链接是否失效；
4. `linked_projects` 是否包含不存在的路径。

---

### 18.2 Skill 删除

增加：

```bash
skm remove api-generator
```

删除：

1. registry 中的记录；
2. registry 中的源文件；
3. 可选清理所有项目中的软链接。

---

### 18.3 Skill 推荐

未来可以根据当前项目类型自动推荐 Skill：

```bash
skm recommend
```

例如：

- 检测到 `package.json`，推荐前端相关 Skill；
- 检测到 `requirements.txt`，推荐 Python 相关 Skill；
- 检测到 `prd.md`，推荐产品分析 Skill。

---

## 19. 总结

`skm` 的 MVP 目标不是做一个复杂平台，而是先解决本地 Skill 管理的核心问题：

```text
统一存放
快速注册
一键关联
中文备注
全局搜索
方便复用
```

第一版只要能稳定完成这几个动作，就已经足够投入日常使用。

后续可以在真实使用中逐步扩展版本管理、团队共享、远程同步和自动推荐能力。
