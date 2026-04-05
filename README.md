# polygon2hydro (p2h)

`polygon2hydro`（`p2h`）用于将 Polygon contest package 转换为 Hydro/HydroOJ 可导入的题目包。
输入为一个包含多道题目的 contest zip，输出为“每道题一个 zip”的 Hydro 导入格式。

## 1. 功能概览

- 从 contest 包自动发现 `problems/<slug>/...` 目录。
- 读取题目元数据、题面、测试数据与附件资源。
- 支持传统题与交互题（根据 `problem.xml` 中 `assets/interactor` 自动识别）。
- 为每道题生成 Hydro 导入包，核心内容包括：
  - `problem.yaml`
  - `problem_zh.md`
  - `testdata/config.yaml`
  - `testdata/testsNN.in/out`
  - `additional_file/*`（若存在）

## 2. 安装与运行

#### 2.1 可编辑安装（推荐）

```bash
python3 -m pip install -e .
```

安装后可直接使用：

```bash
p2h convert ...
```

#### 2.2 直接以模块方式运行

```bash
PYTHONPATH=src python3 -m p2h.cli convert ...
```

## 3. 命令行接口

```bash
p2h convert <contest_zip> -o <output_dir> --pid-start P1145 [options]
```

```bash
p2h statement-md <input_path> [--type auto|html|tex|tex-block] [--lang auto|chinese|english] [-o <output_path>]
```

#### 3.1 参数说明

`convert` 参数：

- `contest_zip`：Polygon contest 包路径。
- `-o, --output`：输出目录（每题输出一个 zip）。
- `--pid-start`：起始 PID（如 `P1145`），后续题目按顺序递增。
- `--owner`：写入 `problem.yaml.owner`，题目上传者 id，默认 `1`。
- `--tag`：可重复指定，写入 `problem.yaml.tag` 列表。
- `--only`：仅转换指定 slug；支持重复传参或逗号分隔。
- `--run-doall`：执行每题 `doall.sh` 生成测试/答案（默认启用）。
- `--no-run-doall`：跳过 `doall.sh`，仅使用已有测试文件。
- `--missing-env {warn,ask,error}`：`doall` 依赖预检查策略；`warn` 仅告警并继续（默认），`ask` 交互确认后继续，`error` 直接失败。
- `--verbose`：输出详细日志。

`statement-md` 参数：
- `input_path`：
  - 文件模式：输入 `.html/.htm/.tex` 文件；
  - 目录模式：输入题目目录（必须包含 `problem.xml`）。
- `--type {auto,html,tex,tex-block}`（仅文件模式生效）：
  - `auto`（默认）：按后缀推断，`.html/.htm` -> `html`，`.tex` -> `tex`；
  - `html`：按 HTML 题面解析；
  - `tex`：按完整 TeX 题面解析（包含 `\section`、`\begin{problem}` 等结构）；
  - `tex-block`：按 TeX 片段解析（适合 `legend.tex/input.tex/output.tex/notes.tex`）。
- `--lang {auto,chinese,english}`（仅目录模式生效）：
  - `auto`（默认）：按比赛级 `statements/` 自动决定；
  - `chinese` / `english`：强制使用指定语言优先级。
- `-o, --output`：
  - 文件模式：可选；不传则输出到 stdout；
  - 目录模式：可选；不传则写入 `<input_path>/problem_zh.md`。

提示：当文件模式使用 `--type auto` 且后缀无法推断类型时，会报错并要求显式指定 `--type`。


## 4. 使用示例

#### 4.1 全量转换

```bash
p2h convert example/polygon-contest-package/contest-56961.zip \
  -o out \
  --pid-start P1000 \
  --owner 1 \
  --tag "校赛" \
  --tag "2026"
```

#### 4.2 按 slug 选择性转换

```bash
p2h convert example/polygon-contest-package/contest-56961.zip \
  -o out-only \
  --pid-start P2000 \
  --only buy-cpu \
  --only colorful-path,kettle
```

#### 4.3 独立试转题面（文件模式，输出到 stdout）

```bash
p2h statement-md problems/a/statements/chinese/problem.html
```

#### 4.4 独立试转题面（文件模式，显式类型并写文件）

```bash
p2h statement-md problems/a/statement-sections/chinese/legend.tex --type tex-block -o legend.md
```

#### 4.5 生成最终题面 problem_zh.md（目录模式）

```bash
p2h statement-md problems/a
```

#### 4.6 目录模式指定语言与输出路径

```bash
p2h statement-md problems/a --lang english -o problem_zh.md
```

## 5. 输出结构示例

#### 5.1 题目包输出结构示例

```text
题目名.zip
└── 1/
    ├── problem.yaml
    ├── problem_zh.md
    ├── testdata/
    │   ├── config.yaml
    │   ├── tests01.in
    │   ├── tests01.out
    │   └── ...
    └── additional_file/
        └── ...
```

## 6. 题面转换说明

当前题面语言由比赛级目录 `statements/` 决定：
- 若存在 `statements/chinese`，则全比赛优先使用中文题面；
- 若不存在中文但存在 `statements/english`，则全比赛使用英文题面；
- 若中英都存在，仍优先中文。

在选定语言下，优先使用 `statement-sections/<language>` 的结构化内容；若缺失则回退到 `problem.xml` 的 `statements` 条目。

若比赛级 `statements/` 未提供可识别语言目录，则按兼容策略回退为“中文优先、英文次之”。

传统题输出模板：
- `# Description`
- `# Format`
  - `## Input`
  - `## Output`
- `# Samples`（`input1/output1`, `input2/output2`, ...）
- `# Note`

交互题输出模板：
- `# Description`
- `# Interaction`
- `# Samples`（`input1/output1`, `input2/output2`, ...）
- `# Note`

交互题会在 `testdata/config.yaml` 中生成：
- `type: interactive`
- `interactor: <from problem.xml assets/interactor/source path filename>`
- `time: <...ms>`（若可提取）
- `memory: <...MB>`（若可提取）
- `subtasks`（单一分组，`cases` 按测试点数量动态生成）

传统题会在 `testdata/config.yaml` 中生成：
- `type: default`
- `checker_type: testlib`
- `checker.file: <from problem.xml assets/checker/source path filename>`
- `time: <...ms>`（若可提取）
- `memory: <...MB>`（若可提取）
- `subtasks`（单一分组，`cases` 按测试点数量动态生成）

此外，传统题会将 checker 相关源文件纳入 `testdata`：
- `<files><executables>`、`<assets><solutions>`、`<assets><checker>` 声明的源文件
- 若 `files/check.cpp` 存在，即使未声明也会额外纳入

若题目中无 `assets/interactor`，则按传统题流程处理。

图片会尽量转换为 Hydro 常用格式，例如：

```html
<center>
<img src="file://1.png"/>
</center>
```

以及带宽度参数的形式：

```html
<center>
<img src="file://1.png" width="80%" />
</center>
```

## 7. 安全说明

`--run-doall` 会执行 contest 包中的 `doall.sh` 及相关脚本。
请仅对**可信来源**的输入包启用该选项，避免对不受信任压缩包直接执行脚本。

执行前会对脚本依赖做预检查（例如 `wine`、`java`、`javac` 等），行为由 `--missing-env` 控制：
- `warn`（默认）：告警后继续执行（适合本地环境可能存在特殊路径/包装器的情况）
- `ask`：先询问是否继续
- `error`：缺依赖即直接失败

注意：该预检查是“静态扫描提示”，并不能覆盖所有 shell 动态分支；最终仍以实际执行结果为准。

## 8. 常见错误

- `unknown slug(s): ...`：`--only` 指定的 slug 不存在于 contest 包中。
- `missing answer for test key ...`：缺少与输入同名的答案文件（如 `x.a` 或 `x.out`）；可启用 `--run-doall` 或先在 Polygon 侧生成测试。
- `missing problem.xml`：题目目录结构不完整。

## 9. 测试

```bash
python3 -m pytest -q
```

若当前环境未安装 `pytest`，可先安装测试依赖后再执行。